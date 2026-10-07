# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "langgraph==1.2.14",
# ]
# ///
"""Spike: LangGraph core. No LLM yet.

Questions:
  1. How does a StateGraph pass state between nodes, how do reducers merge
     updates, how do nodes get run-scoped data (tenant id), and what does
     streaming show while it runs?
  2. How do we branch, and fan work out to many identical employees in
     parallel, then gather the results?

Run:  uv run spikes/langgraph-core/main.py
"""

import operator
import time
from dataclasses import dataclass
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send


class OfficeState(TypedDict):
    goal: str
    # No reducer: a node's return value REPLACES the current value.
    tasks: list[str]
    # Reducer operator.add: a node's return value is APPENDED (old + new).
    log: Annotated[list[str], operator.add]


@dataclass
class RunContext:
    """Immutable, run-scoped data. Not part of state, never checkpointed."""

    tenant_id: str


def print_run(graph, inputs: dict, context: RunContext) -> None:  # type: ignore[no-untyped-def]
    start = time.monotonic()
    for part in graph.stream(
        inputs,
        context=context,
        stream_mode=["updates", "values"],
        version="v2",  # typed parts: {"type", "ns", "data"}
    ):
        t = f"t={time.monotonic() - start:.2f}s"
        if part["type"] == "updates":
            for node, update in part["data"].items():
                print(f"{t} [updates] '{node}' returned: {update}")
        else:
            print(f"{t} [values]  state: {part['data']}\n")


# --- Step 1: linear graph ---------------------------------------------------


def coordinator(state: OfficeState, runtime: Runtime[RunContext]) -> dict:
    tasks = [f"design page for '{state['goal']}'", "write the backend"]
    # Nodes return only the keys they change (a partial update).
    return {
        "tasks": tasks,
        "log": [f"[{runtime.context.tenant_id}] coordinator planned {len(tasks)} tasks"],
    }


def employee(state: OfficeState) -> dict:
    return {
        "tasks": [],  # replaced -> list is now empty
        "log": [f"employee finished: {t}" for t in state["tasks"]],  # appended
    }


def build_linear_graph():  # type: ignore[no-untyped-def]
    builder = StateGraph(OfficeState, context_schema=RunContext)
    builder.add_node("coordinator", coordinator)
    builder.add_node("employee", employee)
    builder.add_edge(START, "coordinator")
    builder.add_edge("coordinator", "employee")
    builder.add_edge("employee", END)
    return builder.compile()  # the builder can't run; compile() makes a runnable graph


# --- Step 2: branch + parallel fan-out with Send ----------------------------

TEAM_SIZE = 10  # ten employees with the same skills


class TaskAssignment(TypedDict):
    """Private input for one employee. Not the graph state: only this employee sees it."""

    employee: str
    task: str


def team_coordinator(state: OfficeState) -> dict:
    if not state["goal"]:
        return {"tasks": [], "log": ["coordinator: no goal given"]}
    tasks = [f"build section {i + 1} of '{state['goal']}'" for i in range(TEAM_SIZE)]
    return {"tasks": tasks, "log": [f"coordinator planned {len(tasks)} tasks"]}


def assign(state: OfficeState) -> list[Send] | Literal["ask_admin"]:
    """Routing function: runs after the coordinator and decides what runs next."""
    if not state["tasks"]:
        return "ask_admin"  # branch: a plain node name
    # Fan out: one Send per task, all start in the same step, in parallel.
    return [
        Send("team_employee", TaskAssignment(employee=f"employee-{i + 1}", task=task))
        for i, task in enumerate(state["tasks"])
    ]


def team_employee(assignment: TaskAssignment) -> dict:
    time.sleep(0.5)  # pretend to work
    return {"log": [f"{assignment['employee']} done: {assignment['task']}"]}


def review(state: OfficeState) -> dict:
    """Fan-in: runs once, after every employee in the step has finished."""
    done = sum(1 for line in state["log"] if " done: " in line)
    return {"log": [f"review: {done}/{len(state['tasks'])} tasks done"]}


def ask_admin(state: OfficeState) -> dict:
    return {"log": ["inbox: 'Please tell us what you want built.'"]}


def build_team_graph():  # type: ignore[no-untyped-def]
    builder = StateGraph(OfficeState)
    builder.add_node("team_coordinator", team_coordinator)
    builder.add_node("team_employee", team_employee)
    builder.add_node("review", review)
    builder.add_node("ask_admin", ask_admin)
    builder.add_edge(START, "team_coordinator")
    # path_map lists possible destinations, so the diagram draws real edges.
    builder.add_conditional_edges("team_coordinator", assign, ["team_employee", "ask_admin"])
    builder.add_edge("team_employee", "review")
    builder.add_edge("review", END)
    builder.add_edge("ask_admin", END)
    return builder.compile()


if __name__ == "__main__":
    print("== Step 1: linear graph ==")
    linear = build_linear_graph()
    print(linear.get_graph().draw_mermaid())
    print_run(linear, {"goal": "LLM wrapper website", "tasks": [], "log": []}, RunContext("tenant-a"))

    print("== Step 2: team graph ==")
    team = build_team_graph()
    print(team.get_graph().draw_mermaid())

    print("-- Run A: a goal -> fan out to 10 employees --")
    result = team.invoke({"goal": "LLM wrapper website", "tasks": [], "log": []})
    print("\n".join(result["log"]))

    print("\n-- Run A again, streamed, to see timing --")
    print_run(team, {"goal": "LLM wrapper website", "tasks": [], "log": []}, RunContext("tenant-a"))

    print("-- Run B: no goal -> branch to the admin's inbox --")
    print("\n".join(team.invoke({"goal": "", "tasks": [], "log": []})["log"]))
