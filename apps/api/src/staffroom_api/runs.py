"""Execute a run: drive the team, record every event, keep the run's status current."""

import logging
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import insert, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from staffroom_api import event_stream
from staffroom_api.agents.checkpoints import thread_id
from staffroom_api.agents.events import InputNeeded, RunFailed, RunFinished, RunWaiting, TeamEvent
from staffroom_api.agents.team import Team
from staffroom_api.db.models import Event, InboxItem, Run
from staffroom_api.db.tenancy import tenant_transaction
from staffroom_api.observability import run_tracing

log = logging.getLogger(__name__)


async def execute_run(
    engine: AsyncEngine,
    redis: Redis,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    team: Team,
    goal: str,
    answers: Mapping[str, str] | None = None,
) -> None:
    """Run (or resume) a run. Safe to call again for the same run: it continues.

    `answers` ({question_id: answer}) resumes a run that paused for the admin.
    """
    # Each write is its own short transaction: nothing is held open while agents think.
    await _set_status(engine, tenant_id, run_id, status="running")
    try:
        with run_tracing(tenant_id, run_id) as callbacks:
            async for event in team.stream(
                goal, thread_id=thread_id(tenant_id, run_id), callbacks=callbacks, answers=answers
            ):
                if isinstance(event, RunFinished):
                    await _set_status(
                        engine, tenant_id, run_id, status="succeeded", summary=event.summary
                    )
                elif isinstance(event, InputNeeded):
                    await _open_inbox_item(engine, tenant_id, run_id, event)
                elif isinstance(event, RunWaiting):
                    # Paused for the admin: the segment ends, nothing is held (ADR-0004).
                    await _set_status(engine, tenant_id, run_id, status="waiting")
                await _record(engine, redis, tenant_id, run_id, event)
    except Exception as exc:
        await fail_run(engine, redis, tenant_id, run_id, exc)


async def fail_run(
    engine: AsyncEngine, redis: Redis, tenant_id: uuid.UUID, run_id: uuid.UUID, exc: Exception
) -> None:
    """Mark the run failed. Full error to server logs only: events reach the UI and must
    not carry secrets, so they get the exception type alone."""
    log.exception("run %s failed", run_id, exc_info=exc)
    await _set_status(engine, tenant_id, run_id, status="failed")
    await _record(engine, redis, tenant_id, run_id, RunFailed(error=type(exc).__name__))


async def _open_inbox_item(
    engine: AsyncEngine, tenant_id: uuid.UUID, run_id: uuid.UUID, event: InputNeeded
) -> None:
    """Idempotent: a resume with some questions still open re-raises those interrupts."""
    async with tenant_transaction(engine, tenant_id) as conn:
        await conn.execute(
            pg_insert(InboxItem)
            .values(
                tenant_id=tenant_id,
                run_id=run_id,
                question_id=event.question_id,
                employee=event.employee,
                question=event.question,
                secret_name=event.secret_name,
            )
            .on_conflict_do_nothing(index_elements=["run_id", "question_id"])
        )


async def _record(
    engine: AsyncEngine, redis: Redis, tenant_id: uuid.UUID, run_id: uuid.UUID, event: TeamEvent
) -> None:
    """Postgres first (durable record), then Redis (live feed)."""
    async with tenant_transaction(engine, tenant_id) as conn:
        event_id = await conn.scalar(
            insert(Event)
            .values(tenant_id=tenant_id, run_id=run_id, type=event.type, data=event.model_dump())
            .returning(Event.id)
        )
    if event_id is None:
        raise RuntimeError("event insert returned no id")
    await event_stream.publish(redis, tenant_id, run_id, event_id, event)


async def _set_status(
    engine: AsyncEngine,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    status: str,
    summary: str | None = None,
) -> None:
    values: dict[str, object] = {"status": status}
    if status in ("succeeded", "failed"):
        values["finished_at"] = datetime.now(UTC)
    if summary is not None:
        values["summary"] = summary
    async with tenant_transaction(engine, tenant_id) as conn:
        await conn.execute(update(Run).where(Run.id == run_id).values(**values))
