import uuid
from datetime import datetime
from functools import partial

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from staffroom_api.agents.events import TeamEvent, team_event
from staffroom_api.agents.models import chat_model
from staffroom_api.agents.team import EmployeeSpec, build_team
from staffroom_api.db.models import Employee, Event, Run
from staffroom_api.db.tenancy import tenant_transaction
from staffroom_api.deps import TenantId, TenantSession
from staffroom_api.runs import execute_run

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
async def start_run(
    body: GoalCreate, tenant_id: TenantId, request: Request, background: BackgroundTasks
) -> RunOut:
    """Start a run for the tenant's whole team; returns at once with the run id.

    The run executes after the response (FastAPI BackgroundTasks, same process).
    Increment 4 moves it to a worker + checkpointer so it survives restarts.
    """
    engine = request.app.state.db
    async with tenant_transaction(engine, tenant_id) as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        employees = [
            EmployeeSpec(name=e.name, skills=e.skills)
            for e in await session.scalars(select(Employee))
        ]
        if not employees:
            raise HTTPException(status.HTTP_409_CONFLICT, "Hire at least one employee first.")
        run = Run(tenant_id=tenant_id, goal=body.goal, status="queued")
        session.add(run)
        await session.flush()
        await session.refresh(run)

    model_name = request.app.state.settings.staffroom_model
    team = build_team(employees, model=partial(chat_model, model_name))
    background.add_task(execute_run, engine, tenant_id, run.id, team, body.goal)
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
