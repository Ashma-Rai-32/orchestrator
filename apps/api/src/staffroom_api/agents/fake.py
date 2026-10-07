"""Deterministic fake chat model for tests, CI and keyless local runs.

langchain-core's fakes replay a fixed script and none implements `bind_tools`
(see docs/frameworks/langchain-models.md). Teams are built from database rows,
so tool names are not known in advance; this fake reacts to whatever is bound:

- coordinator (delegation tools bound) -> call every bound tool once, then summarise
- employee with sandbox tools          -> write_file, then execute, then report
  (sequential, as a real model would: a command must not race the file it reads)
- no tools                             -> report the request as done
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
LIST_WORKSPACE = (
    "node -e \"const fs=require('fs');"
    "console.log('workspace/notes:', fs.readdirSync('/workspace/notes').join(', '))\""
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
        results = [str(m.content) for m in messages if isinstance(m, ToolMessage)]
        if set(self.tool_names) >= SANDBOX_TOOLS:
            return self._sandbox_step(request, results)
        if results:
            return AIMessage(content="All done. " + " | ".join(results))
        if self.tool_names:
            return _calls([(name, {"task": f"{request} [{name}]"}) for name in self.tool_names])
        return AIMessage(content=f"Done: {request}")

    @staticmethod
    def _sandbox_step(request: str, results: list[str]) -> AIMessage:
        if not results:
            note = f"/workspace/notes/{hashlib.sha256(request.encode()).hexdigest()[:8]}.md"
            return _calls([("write_file", {"file_path": note, "content": f"# Task\n{request}\n"})])
        if len(results) == 1:
            return _calls([("execute", {"command": LIST_WORKSPACE})])
        return AIMessage(content=f"Done: {request}. {results[-1].strip()}")


def _calls(calls: list[tuple[str, dict[str, Any]]]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call_{i}"} for i, (name, args) in enumerate(calls)
        ],
    )
