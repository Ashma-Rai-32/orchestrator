"""Browser tools for employees: Microsoft's Playwright MCP server, inside the run's sandbox.

The browser opens sites the agents built, so it is untrusted too: it runs inside the
sandbox container, next to the site. The worker talks to it over stdio through
`docker exec -i` (MCP stdio transport), so no network port is opened anywhere.

langchain-mcp-adapters turns the MCP tools into LangChain tools. One session is kept
open for the whole segment: `MultiServerMCPClient.get_tools()` would start a new
server (and a fresh browser) for every single tool call.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession

KEEPALIVE_SECONDS = 60  # well under the socket proxy's 10-minute idle timeout

PLAYWRIGHT_MCP = [
    "playwright-mcp",
    "--headless",
    "--isolated",  # profile in memory: the sandbox's root filesystem is read-only
    # Chromium's own sandbox needs Linux capabilities we dropped; the container is the sandbox.
    "--no-sandbox",
    "--browser=chromium",
    "--output-dir=/tmp/playwright",
]

# What a tester needs to check a site. Left out on purpose even though the browser is
# sandboxed: arbitrary JS/Playwright code (`browser_run_code_unsafe`, `browser_evaluate`)
# and file uploads. Least privilege for the model, not a security boundary.
ALLOWED_TOOLS = frozenset(
    {
        "browser_navigate",
        "browser_navigate_back",
        "browser_snapshot",  # accessibility tree: how the model "sees" the page
        "browser_take_screenshot",
        "browser_click",
        "browser_type",
        "browser_fill_form",
        "browser_press_key",
        "browser_select_option",
        "browser_hover",
        "browser_wait_for",
        "browser_resize",
        "browser_console_messages",
        "browser_network_requests",
        "browser_tabs",
        "browser_close",
    }
)


@asynccontextmanager
async def browser_tools(container_name: str) -> AsyncIterator[list[BaseTool]]:
    # stdio servers only inherit a few env vars: pass the Docker endpoint explicitly.
    env = {k: v for k in ("PATH", "DOCKER_HOST", "HOME") if (v := os.environ.get(k))}
    client = MultiServerMCPClient(
        {
            "browser": {
                "transport": "stdio",
                "command": "docker",
                "args": ["exec", "-i", container_name, *PLAYWRIGHT_MCP],
                "env": env,
            }
        }
    )
    async with client.session("browser") as session:
        tools = await load_mcp_tools(session)
        keepalive = asyncio.create_task(_keep_alive(session))
        try:
            yield [t for t in tools if t.name in ALLOWED_TOOLS]
        finally:
            keepalive.cancel()


async def _keep_alive(session: ClientSession) -> None:
    """MCP ping while the browser waits for its turn (often the whole build phase).

    Real-model finding: the Docker socket proxy (HAProxy, `timeout client/server 10m`)
    closed the idle `docker exec` stream, and the tester's first browser call failed.
    """
    while True:
        await asyncio.sleep(KEEPALIVE_SECONDS)
        await session.send_ping()
