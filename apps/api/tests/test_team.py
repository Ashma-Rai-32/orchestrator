"""Team builder with the rule-based fake model (no database, no API key)."""

from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from staffroom_api.agents.fake import RuleBasedFakeModel
from staffroom_api.agents.models import chat_model
from staffroom_api.agents.team import EmployeeSpec, TeamResult, build_team, employee_prompt

pytestmark = pytest.mark.anyio

TWELVE = (
    [EmployeeSpec(f"Pixel {i}", ["react", "css"]) for i in range(1, 11)]
    + [EmployeeSpec("Ada", ["nodejs", "ai-integration"])]
    + [EmployeeSpec("Max", ["css", "react", "react"])]  # same set as the Pixels
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def fake() -> BaseChatModel:
    return chat_model("fake")


def test_identical_skill_sets_share_one_tool() -> None:
    team = build_team(TWELVE, model=fake)
    assert sorted(t.name for t in team.tools) == [
        "assign_ai_integration_nodejs",
        "assign_css_react",
    ]
    assert "(11 available;" in next(t.description for t in team.tools if "react" in t.name)


async def test_goal_is_delegated_to_each_pool_and_summarised() -> None:
    team = build_team(TWELVE, model=fake)
    result = await team.run("Build an LLM wrapper site")

    assert {a.employee for a in result.assignments} == {"Pixel 1", "Ada"}
    assert all(a.result.startswith("Done: Build an LLM wrapper site") for a in result.assignments)
    assert result.summary.startswith("All done.")


async def test_pool_rotates_across_runs() -> None:
    team = build_team(TWELVE, model=fake)
    first = await team.run("goal one")
    second = await team.run("goal two")
    assert (_pixel(first), _pixel(second)) == ("Pixel 1", "Pixel 2")


def _pixel(result: TeamResult) -> str:
    return next(a.employee for a in result.assignments if a.employee != "Ada")


def test_empty_team_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one employee"):
        build_team([], model=fake)


def test_employees_with_a_sandbox_are_told_where_the_project_lives() -> None:
    assert "/workspace" in employee_prompt("You build React UIs.", has_sandbox=True)
    assert "/workspace" not in employee_prompt("You build React UIs.", has_sandbox=False)


class _ScriptedCoordinator(GenericFakeChatModel):
    """Replays a fixed script; accepts bind_tools (see docs/frameworks/langchain-models.md)."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_ScriptedCoordinator":
        return self


class _BrokenEmployee(RuleBasedFakeModel):
    def _reply(self, messages: Any) -> Any:
        raise ConnectionError("model server went away")


def _team_with(coordinator_calls: list[str], employee: type[RuleBasedFakeModel]) -> Any:
    """One React employee; the coordinator calls the given tools in one turn."""
    script = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": name, "args": {"task": f"task {i}"}, "id": f"c{i}"}
                    for i, name in enumerate(coordinator_calls)
                ],
            ),
            AIMessage(content="Summary"),
        ]
    )
    made = 0

    def model() -> BaseChatModel:
        nonlocal made
        made += 1  # employees are built first, the coordinator last
        return employee() if made == 1 else _ScriptedCoordinator(messages=script)

    return build_team([EmployeeSpec("Robin", ["react"])], model=model)


async def test_an_employee_works_on_one_task_at_a_time() -> None:
    team = _team_with(["assign_react", "assign_react"], RuleBasedFakeModel)
    events = [e.type async for e in team.stream("two tasks for a pool of one")]
    work = [t for t in events if t.startswith("task_")]
    assert work == ["task_assigned", "task_finished", "task_assigned", "task_finished"]


async def test_a_failed_task_is_reported_and_the_run_continues() -> None:
    team = _team_with(["assign_react"], _BrokenEmployee)
    events = [e async for e in team.stream("goal")]
    failed = [e for e in events if e.type == "task_failed"]
    assert len(failed) == 1
    assert failed[0].error == "ConnectionError"  # type only, never the message
    assert events[-1].type == "run_finished"
