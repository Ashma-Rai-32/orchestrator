"""Team builder with the rule-based fake model (no database, no API key)."""

import pytest
from langchain_core.language_models import BaseChatModel

from staffroom_api.agents.models import chat_model
from staffroom_api.agents.team import EmployeeSpec, TeamResult, build_team

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
    assert "(11 available)" in next(t.description for t in team.tools if "react" in t.name)


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
