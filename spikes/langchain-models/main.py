# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "langchain==1.4.3",
#     "langchain-anthropic==1.7.5",
# ]
# ///
"""Spike: LangChain model interface.

Questions:
  1. Can we pick the model provider from config alone, and swap in a
     deterministic fake model for tests, without changing calling code?
  2. How does tool calling work, and can the fake model take part in it?

Run:  uv run spikes/langchain-models/main.py
Real: STAFFROOM_REAL_MODEL=1 ANTHROPIC_API_KEY=... uv run spikes/langchain-models/main.py
"""

import json
import os
from collections.abc import Sequence
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_core.utils.function_calling import convert_to_openai_tool

# Pinned model ID, not an alias (init_chat_model docs recommend this).
DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"


class FakeToolCallingModel(GenericFakeChatModel):
    """GenericFakeChatModel that accepts bind_tools.

    No fake in langchain-core or langchain-tests implements bind_tools (the base
    class raises NotImplementedError). Tool calls are scripted like any other
    reply, so binding just returns the same model.
    """

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeToolCallingModel":
        return self


def get_model(script: list[AIMessage | str]) -> BaseChatModel:
    """The only place that decides which model we get.

    `script` is the list of replies the fake model plays back in order.
    A real model ignores it and answers for itself.
    """
    if os.environ.get("STAFFROOM_REAL_MODEL") == "1":
        return init_chat_model(os.environ.get("STAFFROOM_MODEL", DEFAULT_MODEL), temperature=0)
    return FakeToolCallingModel(messages=iter(script))


def demo_same_calling_code() -> None:
    print("\n== 1. Same calling code, model chosen by config ==")
    model = get_model(
        script=[
            AIMessage(content="Hi! I'm a fake employee. I always say this first."),
            "And this second.",
        ]
    )
    print(f"model class: {type(model).__name__}")
    for question in ["Who are you?", "Anything else?"]:
        reply = model.invoke(question)
        print(f"Q: {question}\nA: {reply.content}")


def demo_configurable_model() -> None:
    print("\n== 2. One configurable model, provider picked per call ==")
    # No model given -> init_chat_model returns a lazy wrapper. Nothing is
    # constructed (and no API key is needed) until a call supplies the config.
    model = init_chat_model(configurable_fields=("model", "model_provider"), temperature=0)
    print(f"wrapper class: {type(model).__name__}")
    config = {"configurable": {"model": DEFAULT_MODEL}}
    print(f"a call with config={config} would build the real model on demand")


# Synthetic office data.
SKILLS = {"Robin": ["React", "Node.js"], "Sam": ["AI integration"]}


@tool
def get_employee_skills(name: str) -> list[str]:
    """Look up which skills an employee in the office has."""
    return SKILLS.get(name, [])


def demo_tool_calling() -> None:
    print("\n== 3. Tool calling ==")

    # What the model actually receives: name, description and JSON schema,
    # all derived by @tool from the function signature and docstring.
    print("tool schema sent to the model:")
    print(json.dumps(convert_to_openai_tool(get_employee_skills), indent=2))

    model = get_model(
        script=[
            # Turn 1: the model asks us to run a tool instead of answering.
            AIMessage(
                content="",
                tool_calls=[{"name": "get_employee_skills", "args": {"name": "Robin"}, "id": "call_1"}],
            ),
            # Turn 2: having seen the tool result, it answers.
            "Robin knows React and Node.js.",
        ]
    ).bind_tools([get_employee_skills])

    messages: list[BaseMessage] = [HumanMessage("What can Robin do?")]
    ai = model.invoke(messages)
    print(f"\nmodel turn 1 -> tool_calls: {ai.tool_calls}")
    messages.append(ai)

    # The model never runs code. We run each requested tool. Invoking a tool
    # with the ToolCall dict returns a ToolMessage already linked by id.
    # (This loop is what create_agent automates; written out once here to learn it.)
    for call in ai.tool_calls:
        tool_message = get_employee_skills.invoke(call)
        print(f"tool result  -> {type(tool_message).__name__}(content={tool_message.content!r}, "
              f"tool_call_id={tool_message.tool_call_id!r})")
        messages.append(tool_message)

    final = model.invoke(messages)
    print(f"model turn 2 -> {final.content}")


if __name__ == "__main__":
    demo_same_calling_code()
    demo_configurable_model()
    demo_tool_calling()
