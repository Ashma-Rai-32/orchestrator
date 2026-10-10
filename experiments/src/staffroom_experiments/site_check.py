"""Open the built site in the sandbox's browser (the same Playwright MCP the tester uses).

Reads Playwright MCP's Markdown output: navigate reports `HTTP status:` only for
non-2xx responses, and console messages list one `[ERROR]`/exception per entry.
"""

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from langchain_core.tools import BaseTool

from staffroom_api.sandbox.browser import browser_tools

PREVIEW = "http://localhost:4173"
# Browsers ask for /favicon.ico on their own; a missing one is not the site's fault.
IGNORED_ERRORS = re.compile(r"favicon\.ico")
HREF = re.compile(r"""href\s*=\s*["']([^"'#]+)""", re.I)


async def check_site(container: str, path: str, html: str) -> dict[str, Any]:
    """The entry page (HTTP + console errors), then every local page it links to."""
    entry = f"{PREVIEW}{path}"
    async with browser_tools(container) as tools:
        by_name = {t.name: t for t in tools}
        page = await _visit(by_name, entry)
        links = {href: await _visit(by_name, urljoin(entry, href)) for href in local_links(html)}
    return {
        "url": path,
        "http_error": page["http_error"],
        "errors": page["errors"],
        "links": {href: _problems(result) for href, result in links.items()},
    }


def local_links(html: str) -> list[str]:
    """Links to the site's own pages; external sites, mailto: and tel: are out of scope."""
    hrefs = (h.strip() for h in HREF.findall(html))
    return sorted({h for h in hrefs if h and not urlparse(h).scheme and not h.startswith("//")})


async def _visit(tools: dict[str, BaseTool], url: str) -> dict[str, Any]:
    page = _text(await tools["browser_navigate"].ainvoke({"url": url}))
    console = _text(await tools["browser_console_messages"].ainvoke({"level": "error"}))
    status = re.search(r"HTTP status: (.+)", page)
    entries = re.split(r"\n(?=\[ERROR\]|\w*Error:)", console.split("\n\n", 1)[-1])
    errors = [
        e.strip()
        for e in entries
        if ("[ERROR]" in e or "Error:" in e) and not IGNORED_ERRORS.search(e)
    ]
    return {"http_error": status.group(1) if status else None, "errors": errors}


def _problems(result: dict[str, Any]) -> list[str]:
    errors: list[str] = result["errors"]
    return ([result["http_error"]] if result["http_error"] else []) + errors


def _text(result: Any) -> str:
    """MCP tool results arrive as content blocks."""
    if isinstance(result, list):
        return "\n".join(b.get("text", "") for b in result if isinstance(b, dict))
    return str(result)
