"""Execute a run: drive the team, record every event, keep the run's status current."""

import logging
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncEngine

from staffroom_api import event_stream
from staffroom_api.agents.events import RunFailed, RunFinished, TeamEvent
from staffroom_api.agents.team import Team
from staffroom_api.db.models import Event, Run
from staffroom_api.db.tenancy import tenant_transaction

log = logging.getLogger(__name__)


async def execute_run(
    engine: AsyncEngine,
    redis: Redis,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    team: Team,
    goal: str,
) -> None:
    # Each write is its own short transaction: nothing is held open while agents think.
    await _set_status(engine, tenant_id, run_id, status="running")
    try:
        async for event in team.stream(goal):
            if isinstance(event, RunFinished):
                await _set_status(
                    engine, tenant_id, run_id, status="succeeded", summary=event.summary
                )
            await _record(engine, redis, tenant_id, run_id, event)
    except Exception as exc:
        # Full error to server logs only; events reach the UI and must not carry secrets.
        log.exception("run %s failed", run_id)
        await _set_status(engine, tenant_id, run_id, status="failed")
        await _record(engine, redis, tenant_id, run_id, RunFailed(error=type(exc).__name__))


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
