# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "langchain==1.4.3",
#     "langgraph==1.2.14",
# ]
# ///
"""Spike: build a team at runtime from employee records.

Question: given rows like {"name", "skills"} (including 10 employees with the
same skills), how do we turn them into a coordinator + employees with
framework pieces only, without the coordinator drowning in near-identical tools?

Approach (the pattern langgraph-supervisor's README now recommends over the
library): every employee is a `create_agent`; the coordinator is a
`create_agent` whose tools delegate to employees. Employees with the same
skill set share ONE tool (a pool), so tool count = distinct skill sets.

Run:  uv run spikes/team-builder/main.py
"""

import itertools
import json
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool

# --- Synthetic data ---------------------------------------------------------

SKILL_CATALOG = {
    "react": "You build React user interfaces.",
    "css": "You write clean, responsive CSS.",
    "node": "You build Node.js backends and APIs.",
    "ai-integration": "You integrate LLM APIs into products safely.",
}

EMPLOYEES = (
    [{"name": f"Pixel {i}", "skills": ["react", "css"]} for i in range(1, 11)]  # 10 identical
    + [{"name": "Ada", "skills": ["node", "ai-integration"]}]
    + [{"name": "Max", "skills": ["react", "node"]}]
)


# --- Fake model (from the langchain-models spike) ---------------------------


class FakeToolCallingModel(GenericFakeChatModel):
    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeToolCallingModel":
        return self


def fake_employee_model(name: str) -> BaseChatModel:
    return FakeToolCallingModel(messages=itertools.cycle([f"done, signed {name}"]))


# --- Team builder: the only custom logic ------------------------------------


def merged_prompt(skills: list[str]) -> str:
    return "You are an employee at Staffroom.\n" + "\n".join(SKILL_CATALOG[s] for s in skills)


def pool_tool(skills: tuple[str, ...], members: list[dict], agents: dict[str, Any]) -> BaseTool:
    """One delegation tool for all employees sharing a skill set."""
    rotation = itertools.cycle(m["name"] for m in members)  # placeholder for real scheduling

    def delegate(task: str) -> str:
        name = next(rotation)
        result = agents[name].invoke({"messages": [{"role": "user", "content": task}]})
        return f"{name}: {result['messages'][-1].content}"

    slug = re.sub(r"[^a-z0-9_]", "_", "_".join(skills))
    return StructuredTool.from_function(
        delegate,
        name=f"assign_{slug}",
        description=(
            f"Give one task to an employee skilled in {', '.join(skills)} "
            f"({len(members)} available). Call several times in one turn to work in parallel."
        ),
    )


def build_team(
    employees: list[dict],
    employee_model: Callable[[str], BaseChatModel],
    coordinator_model: BaseChatModel,
):  # type: ignore[no-untyped-def]
    agents = {
        e["name"]: create_agent(
            employee_model(e["name"]),
            tools=[],  # M2: tools come from the skill registry
            system_prompt=merged_prompt(e["skills"]),
            middleware=[ModelCallLimitMiddleware(run_limit=10)],  # runaway guard
            name=e["name"],
        )
        for e in employees
    }
    pools: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for e in employees:
        pools[tuple(sorted(e["skills"]))].append(e)

    tools = [pool_tool(skills, members, agents) for skills, members in pools.items()]
    coordinator = create_agent(
        coordinator_model,
        tools=tools,
        system_prompt="You are the coordinator. Split the goal into tasks and assign them.",
        name="coordinator",
    )
    return coordinator, tools


# --- Demo -------------------------------------------------------------------


def schema_chars(tools: list[BaseTool]) -> int:
    return len(json.dumps([convert_to_openai_tool(t) for t in tools]))


if __name__ == "__main__":
    coordinator_script = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "assign_css_react", "args": {"task": "Build the hero section"}, "id": "c1"},
                {"name": "assign_css_react", "args": {"task": "Build the pricing page"}, "id": "c2"},
                {"name": "assign_css_react", "args": {"task": "Build the chat widget"}, "id": "c3"},
                {"name": "assign_ai_integration_node", "args": {"task": "Proxy the LLM API"}, "id": "c4"},
            ],
        ),
        "All four tasks are done.",
    ]
    coordinator, tools = build_team(
        EMPLOYEES, fake_employee_model, FakeToolCallingModel(messages=iter(coordinator_script))
    )

    print(f"== {len(EMPLOYEES)} employees -> {len(tools)} coordinator tools ==")
    for t in tools:
        print(f"  {t.name}: {t.description}")

    per_employee = [
        StructuredTool.from_function(lambda task: task, name=f"assign_{i}", description=e["name"])
        for i, e in enumerate(EMPLOYEES)
    ]
    print(f"\ntool schema size  pooled: {schema_chars(tools)} chars"
          f"   one-tool-per-employee: {schema_chars(per_employee)} chars (grows with headcount)")

    print("\n== Run: coordinator delegates 4 tasks in one turn ==")
    result = coordinator.invoke({"messages": [{"role": "user", "content": "Build an LLM wrapper site"}]})
    for m in result["messages"]:
        if m.type == "tool":
            print(f"  tool result  -> {m.content}")
    print(f"  coordinator -> {result['messages'][-1].content}")

    print("\n== Coordinator graph ==")
    print(coordinator.get_graph().draw_mermaid())
