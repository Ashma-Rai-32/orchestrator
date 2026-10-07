"""Named toolsets that skills can ask for (catalog.toml `tools = [...]`).

A toolset may hold a live session (the browser), so it is opened once per run
segment, and only if some employee on the team needs it.
"""

import logging
from collections.abc import AsyncIterator, Iterable
from contextlib import AsyncExitStack, asynccontextmanager

from deepagents.backends.protocol import SandboxBackendProtocol
from langchain_core.tools import BaseTool

from staffroom_api.sandbox.browser import browser_tools

log = logging.getLogger(__name__)

Toolsets = dict[str, list[BaseTool]]


@asynccontextmanager
async def open_toolsets(
    names: Iterable[str], sandbox: SandboxBackendProtocol | None
) -> AsyncIterator[Toolsets]:
    opened: Toolsets = {}
    async with AsyncExitStack() as stack:
        for name in sorted(set(names)):
            if name == "browser" and sandbox is not None:
                # The browser runs inside the run's sandbox container (ADR-0006 update).
                opened[name] = await stack.enter_async_context(browser_tools(sandbox.id))
            else:
                log.warning(
                    "toolset %r unavailable (sandbox=%s); skills get no %s tools",
                    name,
                    sandbox is not None,
                    name,
                )
        yield opened
