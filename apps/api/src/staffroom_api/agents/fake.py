"""Deterministic fake chat model for tests, CI and keyless local runs.

langchain-core's fakes replay a fixed script and none implements `bind_tools`
(see docs/frameworks/langchain-models.md). Teams are built from database rows,
so tool names are not known in advance; this fake reacts to whatever is bound,
doing what a sensible real model would (sequentially, never racing its own steps):

- coordinator (delegation tools)  -> delegate build work, then testing, then summarise
- tester (browser tools)          -> open the live preview, read the page, report
- builder (sandbox tools)         -> write a page, list the site with node, report
- no tools                        -> report the request as done
"""

import asyncio
import hashlib
from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool

SANDBOX_TOOLS = {"write_file", "execute"}
BROWSER_TOOLS = {"browser_navigate", "browser_snapshot"}
SITE, PORT = "/workspace/site", 4173
LIST_SITE = (
    "node -e \"const fs=require('fs');"
    f"console.log('site pages:', fs.readdirSync('{SITE}').join(', '))\""
)


class RuleBasedFakeModel(BaseChatModel):
    tool_names: tuple[str, ...] = ()
    latency_seconds: float = 0.0  # simulated thinking time, to watch runs unfold

    @property
    def _llm_type(self) -> str:
        return "staffroom-rule-based-fake"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "RuleBasedFakeModel":
        names = tuple(convert_to_openai_tool(t)["function"]["name"] for t in tools)
        return self.model_copy(update={"tool_names": names})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._reply(messages))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        await asyncio.sleep(self.latency_seconds)  # non-blocking, so parallel tasks overlap
        return ChatResult(generations=[ChatGeneration(message=self._reply(messages))])

    def _reply(self, messages: list[BaseMessage]) -> AIMessage:
        request = next(str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage))
        # `.text` joins content blocks; MCP tools return lists of blocks, not strings.
        results = [str(m.text) for m in messages if isinstance(m, ToolMessage)]
        tools = set(self.tool_names)
        if tools >= BROWSER_TOOLS:
            return _tester_step(request, results)
        if tools >= SANDBOX_TOOLS:
            return _builder_step(request, results)
        if tools:
            return _coordinator_step(request, results, self.tool_names)
        return AIMessage(content=f"Done: {request}")


def _coordinator_step(request: str, results: list[str], tool_names: tuple[str, ...]) -> AIMessage:
    build = [t for t in tool_names if "testing" not in t]
    test = [t for t in tool_names if "testing" in t]
    if not results:
        first = build or test
        return _calls([(t, {"task": f"{request} [{t}]"}) for t in first])
    if build and test and len(results) == len(build):
        return _calls([(t, {"task": f"Check the site in a browser [{t}]"}) for t in test])
    return AIMessage(content="All done. " + " | ".join(results))


def _builder_step(request: str, results: list[str]) -> AIMessage:
    if not results:
        page = f"{SITE}/{hashlib.sha256(request.encode()).hexdigest()[:8]}.html"
        html = f"<html><body><h1>{request}</h1></body></html>\n"
        return _calls([("write_file", {"file_path": page, "content": html})])
    if len(results) == 1:
        return _calls([("execute", {"command": LIST_SITE})])
    return AIMessage(content=f"Done: {request}. {results[-1].strip()}")


def _tester_step(request: str, results: list[str]) -> AIMessage:
    steps: list[tuple[str, dict[str, Any]]] = [
        ("browser_wait_for", {"time": 1}),
        # The sandbox serves /workspace on PORT already (sandbox/Dockerfile).
        ("browser_navigate", {"url": f"http://localhost:{PORT}/site/"}),
        ("browser_snapshot", {}),
    ]
    if len(results) < len(steps):
        return _calls([steps[len(results)]])
    seen = [line.strip("- ") for line in results[-1].splitlines() if "link" in line]
    return AIMessage(content=f"Checked in a browser: the site lists {len(seen)} page(s): {seen}")


def _calls(calls: list[tuple[str, dict[str, Any]]]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call_{i}"} for i, (name, args) in enumerate(calls)
        ],
    )
