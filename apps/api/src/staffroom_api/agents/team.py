"""Build a team from employee rows (ADR-0007) and run a goal.

The rest of the app depends only on `Team` / `build_team`; LangGraph and
LangChain stay inside this module and `models.py`.

Topology: a coordinator agent whose tools delegate to employees. Employees with
the same skill set share one tool (a pool), so tool count = distinct skill sets.
"""

import itertools
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool, StructuredTool

from staffroom_api.skills.catalog import merge_skills

COORDINATOR_PROMPT = (
    "You are the coordinator of a team of AI employees. Split the admin's goal into "
    "concrete tasks and assign each one with the matching tool. Call several tools in "
    "one turn when tasks are independent. When all results are in, summarise them."
)
MAX_MODEL_CALLS_PER_RUN = 20  # runaway guard per agent run


@dataclass(frozen=True)
class EmployeeSpec:
    name: str
    skills: list[str]


@dataclass(frozen=True)
class Assignment:
    employee: str
    task: str
    result: str


@dataclass
class TeamResult:
    summary: str
    assignments: list[Assignment] = field(default_factory=list)


class Team(Protocol):
    async def run(self, goal: str) -> TeamResult: ...


ModelFactory = Callable[[], BaseChatModel]


class _LangGraphTeam:
    def __init__(self, employees: list[EmployeeSpec], model: ModelFactory) -> None:
        self._assignments: list[Assignment] = []
        agents = {e.name: self._employee_agent(e, model()) for e in employees}

        pools: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for e in employees:
            pools[merge_skills(e.skills).skill_keys].append(e.name)

        self.tools = [self._pool_tool(skills, names, agents) for skills, names in pools.items()]
        self._coordinator = create_agent(
            model(), tools=self.tools, system_prompt=COORDINATOR_PROMPT, name="coordinator"
        )

    @staticmethod
    def _employee_agent(e: EmployeeSpec, model: BaseChatModel) -> Any:
        return create_agent(
            model,
            tools=[],  # M2: resolved from merge_skills(...).tools
            system_prompt=merge_skills(e.skills).system_prompt,
            middleware=[ModelCallLimitMiddleware(run_limit=MAX_MODEL_CALLS_PER_RUN)],
            name=e.name,
        )

    def _pool_tool(
        self, skills: tuple[str, ...], names: list[str], agents: dict[str, Any]
    ) -> BaseTool:
        rotation = itertools.cycle(names)  # TODO(M1): pick an idle employee, not round-robin

        async def delegate(task: str) -> str:
            name = next(rotation)
            result = await agents[name].ainvoke({"messages": [{"role": "user", "content": task}]})
            answer = str(result["messages"][-1].content)
            self._assignments.append(Assignment(employee=name, task=task, result=answer))
            return f"{name}: {answer}"

        slug = re.sub(r"[^a-z0-9_]", "_", "_".join(skills))[:57]
        return StructuredTool.from_function(
            coroutine=delegate,
            name=f"assign_{slug}",
            description=(
                f"Give one task to an employee skilled in {', '.join(skills)} "
                f"({len(names)} available). Call several times in one turn to work in parallel."
            ),
        )

    async def run(self, goal: str) -> TeamResult:
        self._assignments = []
        result = await self._coordinator.ainvoke({"messages": [{"role": "user", "content": goal}]})
        return TeamResult(
            summary=str(result["messages"][-1].content), assignments=list(self._assignments)
        )


def build_team(employees: list[EmployeeSpec], model: ModelFactory) -> _LangGraphTeam:
    if not employees:
        raise ValueError("a team needs at least one employee")
    return _LangGraphTeam(employees, model)
