import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, WebSocket, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from staffroom_api import event_stream
from staffroom_api.agents.events import TeamEvent, team_event
from staffroom_api.db.models import Employee, Event, Run
from staffroom_api.db.tenancy import tenant_transaction
from staffroom_api.deps import WS_SUBPROTOCOL, TenantId, TenantSession, websocket_principal
from staffroom_api.worker import run_segment

router = APIRouter(tags=["runs"])


class GoalCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)


class RunOut(BaseModel):
    id: uuid.UUID
    goal: str
    status: str
    summary: str | None
    created_at: datetime
    finished_at: datetime | None


class EventOut(BaseModel):
    id: int
    created_at: datetime
    event: TeamEvent


@router.post("/goals", status_code=status.HTTP_202_ACCEPTED)
async def start_run(body: GoalCreate, tenant_id: TenantId, request: Request) -> RunOut:
    """Create a run and enqueue it for a worker (ADR-0004); returns at once."""
    async with tenant_transaction(request.app.state.db, tenant_id) as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        if (await session.scalar(select(Employee.id).limit(1))) is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Hire at least one employee first.")
        run = Run(tenant_id=tenant_id, goal=body.goal, status="queued")
        session.add(run)
        await session.flush()
        await session.refresh(run)

    # After commit, so the worker always finds the run row.
    await run_segment.kiq(str(tenant_id), str(run.id))
    return _run_out(run)


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, session: TenantSession) -> RunOut:
    run = await session.get(Run, run_id)  # RLS: other tenants' runs are invisible -> 404
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")
    return _run_out(run)


@router.get("/runs/{run_id}/events")
async def list_run_events(run_id: uuid.UUID, session: TenantSession) -> list[EventOut]:
    rows = await session.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.id))
    return [
        EventOut(id=e.id, created_at=e.created_at, event=team_event.validate_python(e.data))
        for e in rows
    ]


def _run_out(run: Run) -> RunOut:
    return RunOut(
        id=run.id,
        goal=run.goal,
        status=run.status,
        summary=run.summary,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


TERMINAL_STATUSES = {"succeeded", "failed"}


@router.websocket("/runs/{run_id}/stream")
async def stream_run(websocket: WebSocket, run_id: uuid.UUID) -> None:
    """Live events for one run: full replay first, then live, then the socket closes.

    Auth: the client offers subprotocols ["bearer", <access token>] (browsers cannot
    set an Authorization header on WebSockets, and URLs end up in access logs).
    """
    principal = await websocket_principal(websocket)
    if principal is None:
        await websocket.close(code=4401, reason="Not signed in.")
        return
    tenant_id = principal.tenant_id
    state = websocket.app.state
    async with tenant_transaction(state.db, tenant_id) as conn:
        run = await AsyncSession(bind=conn).get(Run, run_id)
    if run is None:
        await websocket.close(code=4404, reason="Run not found.")  # RLS hides other tenants
        return

    await websocket.accept(subprotocol=WS_SUBPROTOCOL)
    live_feed_gone = run.status in TERMINAL_STATUSES and not await event_stream.exists(
        state.redis, tenant_id, run_id
    )
    if live_feed_gone:
        # Redis stream expired after the run ended: replay the durable record instead.
        async with tenant_transaction(state.db, tenant_id) as conn:
            rows = await conn.execute(
                select(Event.id, Event.data).where(Event.run_id == run_id).order_by(Event.id)
            )
            for event_id, data in rows:
                await websocket.send_json({"id": event_id, "event": data})
    else:
        async for payload in event_stream.follow(state.redis, tenant_id, run_id):
            await websocket.send_json(payload)
    await websocket.close()
