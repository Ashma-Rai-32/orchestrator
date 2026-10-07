# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "langchain==1.4.3",
#     "langchain-anthropic==1.7.5",
#     "pytest==9.1.1",
# ]
# ///
"""Assertions for what the langchain-models spike showed. No API key needed.

Run:  uv run spikes/langchain-models/test_spike.py
Real-model test too:  STAFFROOM_REAL_MODEL=1 ANTHROPIC_API_KEY=... uv run spikes/langchain-models/test_spike.py
"""

import os
import sys
from pathlib import Path

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent))
from main import (  # noqa: E402
    FakeToolCallingModel,
    FlakyReplies,
    Plan,
    get_employee_skills,
    get_model,
)
from langchain.chat_models import init_chat_model  # noqa: E402

PLAN_ARGS = {"summary": "s", "tasks": [{"title": "Build UI", "skill": "React"}]}


def plan_call(args: dict, call_id: str = "p1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": "Plan", "args": args, "id": call_id}])


@pytest.fixture(autouse=True)
def fake_by_default(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if "real_model" not in request.keywords:
        monkeypatch.delenv("STAFFROOM_REAL_MODEL", raising=False)


def test_fake_model_replays_script_in_order() -> None:
    model = get_model(script=["first", "second"])
    assert [model.invoke("q").content for _ in range(2)] == ["first", "second"]


def test_configurable_model_needs_no_key_until_called(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    model = init_chat_model(configurable_fields=("model", "model_provider"))
    assert not isinstance(model, BaseChatModel)  # lazy wrapper, nothing built yet


def test_base_fake_does_not_support_bind_tools() -> None:
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    with pytest.raises(NotImplementedError):
        GenericFakeChatModel(messages=iter([])).bind_tools([get_employee_skills])


def test_tool_call_round_trip() -> None:
    call = {"name": "get_employee_skills", "args": {"name": "Robin"}, "id": "call_1"}
    model = get_model(script=[AIMessage(content="", tool_calls=[call]), "done"])
    ai = model.bind_tools([get_employee_skills]).invoke([HumanMessage("What can Robin do?")])

    result = get_employee_skills.invoke(ai.tool_calls[0])

    assert isinstance(result, ToolMessage)
    assert result.tool_call_id == "call_1"
    assert result.content == ["React", "Node.js"]  # list in, list out (see gotchas)


def test_structured_output_returns_pydantic_object() -> None:
    plan = get_model(script=[plan_call(PLAN_ARGS)]).with_structured_output(Plan).invoke("goal")
    assert isinstance(plan, Plan)
    assert plan.tasks[0].skill == "React"


def test_structured_output_raises_on_invalid_by_default() -> None:
    model = get_model(script=[plan_call({"summary": "s", "tasks": []})])
    with pytest.raises(ValidationError):
        model.with_structured_output(Plan).invoke("goal")


def test_structured_output_include_raw_captures_error() -> None:
    model = get_model(script=[plan_call({"summary": "s", "tasks": []})])
    result = model.with_structured_output(Plan, include_raw=True).invoke("goal")
    assert result["parsed"] is None
    assert isinstance(result["parsing_error"], ValidationError)
    assert isinstance(result["raw"], AIMessage)


def test_with_retry_retries_until_success() -> None:
    replies = FlakyReplies(failures=2, reply="ok")
    model = FakeToolCallingModel(messages=replies).with_retry(
        retry_if_exception_type=(ConnectionError,), stop_after_attempt=3, wait_exponential_jitter=False
    )
    assert model.invoke("q").content == "ok"
    assert replies.calls == 3


def test_with_retry_gives_up_after_limit() -> None:
    model = FakeToolCallingModel(messages=FlakyReplies(failures=5, reply="ok")).with_retry(
        retry_if_exception_type=(ConnectionError,), stop_after_attempt=3, wait_exponential_jitter=False
    )
    with pytest.raises(ConnectionError):
        model.invoke("q")


def test_with_fallbacks_uses_backup_and_is_no_longer_a_chat_model() -> None:
    primary = FakeToolCallingModel(messages=FlakyReplies(failures=99, reply=""))
    backup = FakeToolCallingModel(messages=iter(["backup"]))
    resilient = primary.with_fallbacks([backup], exceptions_to_handle=(ConnectionError,))
    assert resilient.invoke("q").content == "backup"
    assert not isinstance(resilient, BaseChatModel)


@pytest.mark.real_model
@pytest.mark.skipif(os.environ.get("STAFFROOM_REAL_MODEL") != "1", reason="real model is opt-in")
def test_real_model_returns_structured_plan() -> None:
    plan = get_model(script=[]).with_structured_output(Plan).invoke(
        "Goal: build me an LLM wrapper website. Plan 2-4 tasks."
    )
    assert isinstance(plan, Plan)
    assert plan.tasks


if __name__ == "__main__":
    # This file imports its deps before pytest starts, hence the rewrite-warning filter.
    sys.exit(pytest.main([
        __file__, "-v", "-p", "no:cacheprovider",
        "-W", "ignore::pytest.PytestAssertRewriteWarning",
        "-o", "markers=real_model: calls a real LLM provider",
    ]))
