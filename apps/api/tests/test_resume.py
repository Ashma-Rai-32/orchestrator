"""Durability: a run interrupted mid-way resumes from its checkpoint (Postgres, RLS)."""

import uuid
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import BaseMessage, ToolMessage

from staffroom_api.agents.checkpoints import run_checkpointer, thread_id
from staffroom_api.agents.events import RunResumed, TaskAssigned, TeamEvent
from staffroom_api.agents.fake import RuleBasedFakeModel
from staffroom_api.agents.team import EmployeeSpec, build_team
from staffroom_api.settings import Settings
from tests.helpers import new_tenant, start_run

pytestmark = pytest.mark.anyio

TEAM = [EmployeeSpec("Robin", ["react"]), EmployeeSpec("Ada", ["nodejs"])]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class CrashOnceBeforeSummary(RuleBasedFakeModel):
    """Simulates a worker dying after the employees finished, before the summary."""

    # Class-level on purpose: pydantic copies field values (and bind_tools copies the
    # model), so a per-instance flag would reset on every copy.
    crashed: ClassVar[bool] = False

    def _reply(self, messages: list[BaseMessage]) -> Any:
        if isinstance(messages[-1], ToolMessage) and not CrashOnceBeforeSummary.crashed:
            CrashOnceBeforeSummary.crashed = True
            raise ConnectionError("worker died")
        return super()._reply(messages)


async def collect(stream: Any) -> list[TeamEvent]:
    return [event async for event in stream]


async def test_resumes_without_redoing_finished_tasks(
    api_settings: Settings, client: TestClient
) -> None:
    acme = new_tenant(client, "Acme").id
    thread = thread_id(acme, uuid.uuid4())
    CrashOnceBeforeSummary.crashed = False

    def model() -> RuleBasedFakeModel:
        return CrashOnceBeforeSummary()

    async with run_checkpointer(api_settings, acme) as saver:
        team = build_team(TEAM, model=model, checkpointer=saver)
        first: list[TeamEvent] = []
        with pytest.raises(ConnectionError):
            async for event in team.stream("Build a site", thread_id=thread):
                first.append(event)
        assert sum(isinstance(e, TaskAssigned) for e in first) == 2  # both tasks done

    # "Another worker": new team object, new connection, same thread id.
    async with run_checkpointer(api_settings, acme) as saver:
        team = build_team(TEAM, model=model, checkpointer=saver)
        second = await collect(team.stream("Build a site", thread_id=thread))

    assert isinstance(second[0], RunResumed)
    assert not any(isinstance(e, TaskAssigned) for e in second)  # no work redone
    assert second[-1].type == "run_finished"


async def test_checkpoints_are_isolated_between_tenants(
    api_settings: Settings, client: TestClient
) -> None:
    acme_headers, globex_headers = new_tenant(client, "Acme"), new_tenant(client, "Globex")
    acme, globex = acme_headers.id, globex_headers.id
    run_id = uuid.UUID(start_run(client, acme_headers))
    config = {"configurable": {"thread_id": thread_id(acme, run_id)}}

    async with run_checkpointer(api_settings, acme) as saver:
        assert await saver.aget_tuple(config) is not None  # type: ignore[arg-type]
    async with run_checkpointer(api_settings, globex) as saver:
        assert await saver.aget_tuple(config) is None  # type: ignore[arg-type]
