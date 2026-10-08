"""deepagents sandbox backend on local Docker (ADR-0006). Development and CI only.

Isolation is entirely Docker configuration (see `_HARDENING`); this module only
maps deepagents' four primitives onto the Docker API. Production uses E2B.
"""

import contextlib
import io
import shlex
import tarfile
import time
import uuid
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

import docker
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox
from docker.errors import NotFound

from staffroom_api.secrets import mask

WORKSPACE = "/workspace"
_GO_MODE_DIR = 1 << 31  # Docker's stat `mode` is Go's os.FileMode
MAX_OUTPUT_CHARS = 30_000
DEFAULT_TIMEOUT_SECONDS = 120

# Docker's own isolation controls; no custom isolation logic (ADR-0006).
_HARDENING: dict[str, Any] = {
    "user": "node",
    "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges:true"],
    "read_only": True,  # root filesystem; /workspace volume and /tmp are writable
    "tmpfs": {"/tmp": "rw,nosuid,size=512m"},  # noqa: S108  (inside the sandbox, not our host)
    "mem_limit": "1g",
    "nano_cpus": 1_000_000_000,  # 1 CPU
    "pids_limit": 256,
}


class DockerSandbox(BaseSandbox):
    """One container + one named volume per run. Re-attached by name after a crash."""

    def __init__(
        self,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        image: str,
        runtime: str | None = None,
        client: docker.DockerClient | None = None,
        secrets: Mapping[str, str] | None = None,
    ) -> None:
        self._docker = client or docker.from_env()
        # Tenant secrets (ADR-0009): env vars for each command, masked in what comes back.
        self._secrets = dict(secrets or {})
        self._name = f"staffroom-sbx-{run_id}"
        self._volume = f"staffroom-ws-{run_id}"
        self._container = self._attach_or_create(tenant_id, run_id, image, runtime)

    @property
    def id(self) -> str:
        return self._name

    def _attach_or_create(
        self, tenant_id: uuid.UUID, run_id: uuid.UUID, image: str, runtime: str | None
    ) -> Any:
        try:
            container = self._docker.containers.get(self._name)
            if container.status != "running":
                container.start()
            return container
        except NotFound:
            pass
        labels = {"staffroom.tenant": str(tenant_id), "staffroom.run": str(run_id)}
        volume = self._docker.volumes.create(name=self._volume, labels=labels)
        return self._docker.containers.run(
            image,
            name=self._name,
            detach=True,
            labels=labels,
            volumes={volume.name: {"bind": WORKSPACE, "mode": "rw"}},
            working_dir=WORKSPACE,
            runtime=runtime,
            **_HARDENING,
        )

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        seconds = timeout or DEFAULT_TIMEOUT_SECONDS
        # coreutils `timeout` inside the sandbox enforces the limit (exit code 124).
        wrapped = ["timeout", "--kill-after=5", str(seconds), "sh", "-c", command]
        # Secrets go in per command (Docker exec `environment`), never into the container
        # config, so `docker inspect` of the sandbox does not reveal them.
        result = self._container.exec_run(
            wrapped, workdir=WORKSPACE, demux=False, environment=self._secrets
        )
        output = mask((result.output or b"").decode("utf-8", errors="replace"), self._secrets)
        truncated = len(output) > MAX_OUTPUT_CHARS
        return ExecuteResponse(
            output=output[:MAX_OUTPUT_CHARS], exit_code=result.exit_code, truncated=truncated
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses = []
        for path, content in files:
            target = PurePosixPath(path)
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w") as tar:
                info = tarfile.TarInfo(target.name)
                info.size, info.uid, info.gid, info.mode = len(content), 1000, 1000, 0o644
                info.mtime = int(time.time())  # tar defaults to 1970, confusing build tools
                tar.addfile(info, io.BytesIO(content))
            parent = str(target.parent)
            self.execute(f"mkdir -p {shlex.quote(parent)}")
            ok = self._container.put_archive(parent, buffer.getvalue())
            responses.append(
                FileUploadResponse(path=path, error=None if ok else "permission_denied")
            )
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses = []
        for path in paths:
            try:
                stream, stat = self._container.get_archive(path)
            except NotFound:
                responses.append(FileDownloadResponse(path=path, error="file_not_found"))
                continue
            if stat["mode"] & _GO_MODE_DIR:
                responses.append(FileDownloadResponse(path=path, error="is_directory"))
                continue
            with tarfile.open(fileobj=io.BytesIO(b"".join(stream))) as tar:
                member = tar.extractfile(tar.getmembers()[0])
                content = member.read() if member else None
            if content is not None and self._secrets:
                # Text files: mask secret values, as for command output. Binary: left as is.
                with contextlib.suppress(UnicodeDecodeError):
                    content = mask(content.decode("utf-8"), self._secrets).encode("utf-8")
            responses.append(FileDownloadResponse(path=path, content=content))
        return responses

    def close(self, *, keep_workspace: bool = True) -> None:
        """Remove the container. The workspace volume is kept for deploy/inspection."""
        self._container.remove(force=True)
        if not keep_workspace:
            self._docker.volumes.get(self._volume).remove()
