"""Deploy with admin approval (roadmap M6.3): nothing goes public without a yes.

`deploy_site` copies the built site out of the sandbox into a private preview folder,
then pauses the run (LangGraph interrupt) with an approval request in the admin's inbox.
Only an approval copies the preview to the public path. A static server (Caddy, see
compose.yaml) serves both folders of the shared `sites` volume.
"""

import hashlib
import re
import shutil
from pathlib import Path, PurePosixPath

from deepagents.backends.protocol import SandboxBackendProtocol
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import interrupt

MAX_FILES = 300
MAX_BYTES = 25 * 1024 * 1024
APPROVE = "approved"

DEPLOY_DOC = (
    "Publish the finished website. Call this only when the site works and has an "
    "index.html at the top of `folder`. The admin first sees a private preview and must "
    "approve it; you get back the public URL, or the admin's reason for rejecting it."
)


class SiteHost:
    """Folders served by the static server: previews/<token>/ (private), sites/<slug>/."""

    def __init__(self, root: Path, public_url: str) -> None:
        self.root, self.public_url = root, public_url.rstrip("/")

    def preview_url(self, token: str) -> str:
        return f"{self.public_url}/previews/{token}/"

    def site_url(self, slug: str) -> str:
        return f"{self.public_url}/sites/{slug}/"

    def write_preview(self, token: str, files: dict[str, bytes]) -> None:
        target = self.root / "previews" / token
        shutil.rmtree(target, ignore_errors=True)  # idempotent: the tool re-runs on resume
        for relative, content in files.items():
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    def publish(self, token: str, slug: str) -> None:
        """Copy, then swap: visitors never see a half-copied site."""
        staging = self.root / "sites" / f".{slug}.staging"
        live = self.root / "sites" / slug
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(self.root / "previews" / token, staging)
        shutil.rmtree(live, ignore_errors=True)
        staging.rename(live)


def site_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "site"


def deploy_tool(
    employee: str, sandbox: SandboxBackendProtocol, sites: SiteHost, slug: str
) -> BaseTool:
    def deploy_site(runtime: ToolRuntime, summary: str, folder: str = "/workspace/site") -> str:
        """`summary`: one sentence for the admin about what is being published."""
        files = _collect(sandbox, folder)
        if "index.html" not in files:
            return f"Not deployed: {folder} has no index.html at its top level."
        # Deterministic per tool call (on resume this tool runs again from the top and must
        # rebuild the *same* preview), but unique and unguessable across runs and tenants:
        # tool call ids alone repeat (e.g. "call_0"); the thread id holds random UUIDs.
        thread = (runtime.config.get("configurable") or {}).get("thread_id", "")
        token = hashlib.sha256(f"{thread}|{runtime.tool_call_id}".encode()).hexdigest()[:32]
        sites.write_preview(token, files)
        decision = str(
            interrupt(
                {
                    "employee": employee,
                    "question": f"{employee} wants to publish the website: {summary}",
                    "kind": "approval",
                    "preview_url": sites.preview_url(token),
                }
            )
        )
        if decision != APPROVE:
            return f"The admin did not approve publishing. {decision}"
        sites.publish(token, slug)
        return f"Published at {sites.site_url(slug)}"

    return StructuredTool.from_function(deploy_site, name="deploy_site", description=DEPLOY_DOC)


def _collect(sandbox: SandboxBackendProtocol, folder: str) -> dict[str, bytes]:
    """Read the site through the sandbox protocol only (works for any backend). Downloads
    are secret-masked, so a key written into a file can never be published."""
    root = PurePosixPath(folder)
    found = sandbox.glob("**/*", path=folder)
    paths = [f["path"] for f in (found.matches or []) if not f.get("is_dir")][:MAX_FILES]
    files: dict[str, bytes] = {}
    total = 0
    for result in sandbox.download_files(paths):
        if result.content is None:
            continue
        relative = PurePosixPath(result.path).relative_to(root)
        if ".." in relative.parts or relative.is_absolute():
            continue  # never write outside the preview folder
        total += len(result.content)
        if total > MAX_BYTES:
            break
        files[str(relative)] = result.content
    return files
