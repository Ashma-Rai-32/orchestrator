"""Open the built site in the sandbox's browser (the same Playwright MCP the tester uses).

Reads Playwright MCP's Markdown output: navigate reports `HTTP status:` only for
non-2xx responses, and console messages list one `[ERROR]`/exception per entry.
"""

import re
from typing import Any

from staffroom_api.sandbox.browser import browser_tools

PREVIEW = "http://localhost:4173"
# Browsers ask for /favicon.ico on their own; a missing one is not the site's fault.
IGNORED_ERRORS = re.compile(r"favicon\.ico")


async def check_site(container: str, path: str) -> dict[str, Any]:
    async with browser_tools(container) as tools:
        by_name = {t.name: t for t in tools}
        page = _text(await by_name["browser_navigate"].ainvoke({"url": f"{PREVIEW}{path}"}))
        console = _text(await by_name["browser_console_messages"].ainvoke({"level": "error"}))
    status = re.search(r"HTTP status: (.+)", page)
    entries = re.split(r"\n(?=\[ERROR\]|\w*Error:)", console.split("\n\n", 1)[-1])
    errors = [
        e.strip()
        for e in entries
        if ("[ERROR]" in e or "Error:" in e) and not IGNORED_ERRORS.search(e)
    ]
    return {"url": path, "http_error": status.group(1) if status else None, "errors": errors}


def _text(result: Any) -> str:
    """MCP tool results arrive as content blocks."""
    if isinstance(result, list):
        return "\n".join(b.get("text", "") for b in result if isinstance(b, dict))
    return str(result)
