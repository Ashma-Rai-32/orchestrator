"""Run benchmark briefs against an agent configuration, scored in Langfuse (ADR-0010).

    uv run python -m staffroom_experiments fake-duo
    uv run python -m staffroom_experiments flash-lite-duo --only coffee-landing

The agent system runs in-process (same team builder, sandbox and toolsets as the
worker); the HTTP API, database, auth and queue are deliberately out of the loop.
"""

import asyncio
import time
import tomllib
import uuid
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langfuse.experiment import LocalExperimentItem
from langfuse.langchain import CallbackHandler
from langgraph.checkpoint.memory import InMemorySaver

from staffroom_api.agents.models import chat_model
from staffroom_api.agents.team import EmployeeSpec, build_team, toolsets_needed
from staffroom_api.agents.toolsets import open_toolsets
from staffroom_api.sandbox.docker_backend import DockerSandbox

HERE = Path(__file__).parent
SITE_ENTRY_POINTS = ("/workspace/site/index.html", "/workspace/index.html")


@dataclass(frozen=True)
class Config:
    name: str
    model: str
    team: list[EmployeeSpec]
    fallbacks: list[str] = field(default_factory=list)
    requests_per_second: float | None = None
    description: str = ""


def load_configs() -> dict[str, Config]:
    raw = tomllib.loads((HERE / "configs.toml").read_text())
    return {
        name: Config(
            name=name,
            model=c["model"],
            team=[EmployeeSpec(m["name"], m["skills"]) for m in c["team"]],
            fallbacks=c.get("fallbacks", []),
            requests_per_second=c.get("requests_per_second"),
            description=c.get("description", ""),
        )
        for name, c in raw.items()
    }


def load_benchmarks(only: list[str] | None = None) -> list[LocalExperimentItem]:
    """Langfuse experiment items: input = brief, expected_output = words the page needs."""
    raw = tomllib.loads((HERE / "benchmarks.toml").read_text())
    return [
        LocalExperimentItem(
            input=b["goal"], expected_output=b["expect"], metadata={"benchmark": key}
        )
        for key, b in raw.items()
        if not only or key in only
    ]


async def run_brief(config: Config, goal: str, image: str, tracing: bool) -> dict[str, Any]:
    """One brief, one fresh sandbox; returns what the evaluators look at."""
    sandbox = await asyncio.to_thread(DockerSandbox, uuid.uuid4(), uuid.uuid4(), image=image)
    try:
        async with open_toolsets(toolsets_needed(config.team), sandbox) as toolsets:
            team = build_team(
                config.team,
                model=partial(chat_model, config.model, config.requests_per_second),
                fallbacks=lambda: [
                    chat_model(m, config.requests_per_second) for m in config.fallbacks
                ],
                checkpointer=InMemorySaver(),
                sandbox=sandbox,
                toolsets=toolsets,
            )
            callbacks: list[BaseCallbackHandler] = [CallbackHandler()] if tracing else []
            started = time.monotonic()
            events = [
                e.model_dump()
                async for e in team.stream(
                    goal, thread_id=f"eval:{uuid.uuid4()}", callbacks=callbacks
                )
            ]
            seconds = time.monotonic() - started
        found = await asyncio.to_thread(sandbox.download_files, list(SITE_ENTRY_POINTS))
        index_html = next((f.content.decode("utf-8", "replace") for f in found if f.content), None)
    finally:
        await asyncio.to_thread(sandbox.close, keep_workspace=False)
    summary = events[-1].get("summary", "") if events else ""
    return {"events": events, "summary": summary, "index_html": index_html, "seconds": seconds}
