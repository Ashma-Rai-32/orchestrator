"""Run benchmark briefs against an agent configuration, scored in Langfuse (ADR-0010).

    uv run python -m staffroom_experiments fake-duo
    uv run --env-file .env python -m staffroom_experiments flash-lite-duo --only coffee-landing
    (real models read their API key from .env; uv loads it into the environment)

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

from langchain_core.callbacks import BaseCallbackHandler, UsageMetadataCallbackHandler
from langfuse.experiment import LocalExperimentItem
from langfuse.langchain import CallbackHandler
from langgraph.checkpoint.memory import InMemorySaver

from staffroom_api.agents.models import chat_model
from staffroom_api.agents.team import EmployeeSpec, build_team, toolsets_needed
from staffroom_api.agents.toolsets import open_toolsets
from staffroom_api.sandbox.docker_backend import DockerSandbox
from staffroom_experiments.site_check import check_site

HERE = Path(__file__).parent
SITE_ENTRY_POINTS = ("/workspace/site/index.html", "/workspace/index.html")


class ToolLog(BaseCallbackHandler):
    """Names of the tools actually called, by every agent: the evidence for the honesty score."""

    run_inline = True  # append in order, on the event loop

    def __init__(self) -> None:
        self.names: list[str] = []

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        self.names.append((serialized or {}).get("name") or kwargs.get("name") or "?")


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
            usage = UsageMetadataCallbackHandler()  # tokens per model, across every call
            tool_log = ToolLog()
            callbacks: list[BaseCallbackHandler] = [
                usage,
                tool_log,
                *([CallbackHandler()] if tracing else []),
            ]
            started = time.monotonic()
            events = [
                e.model_dump()
                async for e in team.stream(
                    goal, thread_id=f"eval:{uuid.uuid4()}", callbacks=callbacks
                )
            ]
            seconds = time.monotonic() - started
        found = await asyncio.to_thread(sandbox.download_files, list(SITE_ENTRY_POINTS))
        entry = next((f for f in found if f.content), None)
        index_html = entry.content.decode("utf-8", "replace") if entry and entry.content else None
        site = None
        if entry:
            # /workspace/site/index.html is served at /site/, /workspace/index.html at /.
            site = await check_site(
                sandbox.id, entry.path.removeprefix("/workspace").removesuffix("index.html")
            )
    finally:
        await asyncio.to_thread(sandbox.close, keep_workspace=False)
    summary = events[-1].get("summary", "") if events else ""
    return {
        "events": events,
        "summary": summary,
        "index_html": index_html,
        "site": site,
        "seconds": seconds,
        "usage": {model: dict(u) for model, u in usage.usage_metadata.items()},
        "tools": tool_log.names,
    }
