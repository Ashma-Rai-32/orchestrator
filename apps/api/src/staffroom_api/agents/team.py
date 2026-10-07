"""Build a team from employee rows (ADR-0007) and run a goal.

The rest of the app depends only on `Team` / `build_team` and the events in
`events.py`; LangGraph and LangChain stay inside this module and `models.py`.

Topology: a coordinator agent whose tools delegate to employees. Employees with
the same skill set share one tool (a pool), so tool count = distinct skill sets.
"""

import itertools
import re
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from deepagents.backends.protocol import SandboxBackendProtocol
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.prebuilt import ToolRuntime

from staffroom_api.agents.events import (
    RunFinished,
    RunResumed,
    RunStarted,
    TaskAssigned,
    TaskFinished,
    TeamEvent,
    team_event,
)
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
    def stream(
        self,
        goal: str,
        thread_id: str | None = None,
        callbacks: list[BaseCallbackHandler] | None = None,
    ) -> AsyncIterator[TeamEvent]: ...
    async def run(self, goal: str) -> TeamResult: ...


ModelFactory = Callable[[], BaseChatModel]


class _LangGraphTeam:
    def __init__(
        self,
        employees: list[EmployeeSpec],
        model: ModelFactory,
        checkpointer: BaseCheckpointSaver[Any] | None,
        sandbox: SandboxBackendProtocol | None,
        toolsets: Mapping[str, list[BaseTool]],
    ) -> None:
        agents = {e.name: self._employee_agent(e, model(), sandbox, toolsets) for e in employees}

        pools: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for e in employees:
            pools[merge_skills(e.skills).skill_keys].append(e.name)

        self.tools = [_pool_tool(skills, names, agents) for skills, names in pools.items()]
        # Only the coordinator is checkpointed: its checkpoints record which delegations
        # finished, so a resumed run re-runs only the unfinished ones.
        self._coordinator = create_agent(
            model(),
            tools=self.tools,
            system_prompt=COORDINATOR_PROMPT,
            name="coordinator",
            checkpointer=checkpointer,
        )

    @staticmethod
    def _employee_agent(
        e: EmployeeSpec,
        model: BaseChatModel,
        sandbox: SandboxBackendProtocol | None,
        toolsets: Mapping[str, list[BaseTool]],
    ) -> Any:
        profile = merge_skills(e.skills)
        # Skill-specific tools, e.g. the browser for `testing` (catalog.toml `tools`).
        skill_tools = [tool for name in profile.tools for tool in toolsets.get(name, [])]
        middleware: list[Any] = [ModelCallLimitMiddleware(run_limit=MAX_MODEL_CALLS_PER_RUN)]
        if sandbox is not None:
            # deepagents: ls/read_file/write_file/edit_file/glob/grep/execute on the run's
            # sandbox. All employees of a run share one workspace (they build one site).
            middleware.append(FilesystemMiddleware(backend=sandbox))
        return create_agent(
            model,
            tools=skill_tools,
            system_prompt=profile.system_prompt,
            middleware=middleware,
            name=e.name,
            checkpointer=False,  # don't inherit the coordinator's; a task is redone as a whole
        )

    async def stream(
        self,
        goal: str,
        thread_id: str | None = None,
        callbacks: list[BaseCallbackHandler] | None = None,
    ) -> AsyncIterator[TeamEvent]:
        """Yield domain events while the team works.

        Tools emit task events on LangGraph's `custom` stream; `values` gives the
        final state, whose last message is the coordinator's summary.

        With a checkpointer and `thread_id`, an interrupted run resumes from its
        last checkpoint: input `None` tells LangGraph to continue, not restart.
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}} if thread_id else {}
        # Tracing callbacks; employees' nested runs inherit them through the run context.
        config["callbacks"] = callbacks or []
        saved = await self._coordinator.aget_state(config) if thread_id else None
        if saved is not None and saved.next:
            yield RunResumed(from_step=", ".join(saved.next))
            inputs: Any = None
        else:
            yield RunStarted(goal=goal)
            inputs = {"messages": [{"role": "user", "content": goal}]}

        final: Any = {}
        async for part in self._coordinator.astream(
            inputs, config, stream_mode=["custom", "values"], version="v2"
        ):
            if part["type"] == "custom":
                yield team_event.validate_python(part["data"])
            elif part["type"] == "values":
                final = part["data"]
        yield RunFinished(summary=str(final["messages"][-1].text))

    async def run(self, goal: str) -> TeamResult:
        """Convenience: consume the stream and return the outcome."""
        result = TeamResult(summary="")
        open_tasks: dict[str, str] = {}  # employee -> task (one task per employee at a time)
        async for event in self.stream(goal):
            if isinstance(event, TaskAssigned):
                open_tasks[event.employee] = event.task
            elif isinstance(event, TaskFinished):
                task = open_tasks.pop(event.employee)
                result.assignments.append(Assignment(event.employee, task, event.result))
            elif isinstance(event, RunFinished):
                result.summary = event.summary
        return result


def _pool_tool(skills: tuple[str, ...], names: list[str], agents: dict[str, Any]) -> BaseTool:
    """One delegation tool for all employees sharing a skill set."""
    rotation = itertools.cycle(names)  # TODO(M1): pick an idle employee, not round-robin

    async def delegate(task: str, runtime: ToolRuntime) -> str:
        name = next(rotation)
        emit = runtime.stream_writer  # a plain callable (docstring's `.write` is wrong)
        emit(TaskAssigned(employee=name, task=task).model_dump())
        result = await agents[name].ainvoke({"messages": [{"role": "user", "content": task}]})
        # .text joins content blocks: real models (and MCP tools) may return lists of blocks.
        answer = str(result["messages"][-1].text)
        emit(TaskFinished(employee=name, result=answer).model_dump())
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


def build_team(
    employees: list[EmployeeSpec],
    model: ModelFactory,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    sandbox: SandboxBackendProtocol | None = None,
    toolsets: Mapping[str, list[BaseTool]] | None = None,
) -> _LangGraphTeam:
    if not employees:
        raise ValueError("a team needs at least one employee")
    return _LangGraphTeam(employees, model, checkpointer, sandbox, toolsets or {})


def toolsets_needed(employees: list[EmployeeSpec]) -> set[str]:
    """Which named toolsets the team's skills ask for (open only those)."""
    return {name for e in employees for name in merge_skills(e.skills).tools}
