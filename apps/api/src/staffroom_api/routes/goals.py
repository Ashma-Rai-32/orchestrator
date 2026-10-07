from functools import partial

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from staffroom_api.agents.models import chat_model
from staffroom_api.agents.team import EmployeeSpec, TeamResult, build_team
from staffroom_api.db.models import Employee
from staffroom_api.db.tenancy import tenant_transaction
from staffroom_api.deps import TenantId

router = APIRouter(tags=["goals"])


class GoalCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)


@router.post("/goals")
async def run_goal(body: GoalCreate, tenant_id: TenantId, request: Request) -> TeamResult:
    """Run a goal with the tenant's whole team and wait for the result.

    Synchronous for now. Increment 3 adds live events; increment 4 moves runs
    to a background worker so they survive the request (and the admin) leaving.
    """
    # Short transaction: never hold a DB transaction open while agents work.
    async with tenant_transaction(request.app.state.db, tenant_id) as conn:
        rows = await AsyncSession(bind=conn).scalars(select(Employee))
        employees = [EmployeeSpec(name=e.name, skills=e.skills) for e in rows]
    if not employees:
        raise HTTPException(status.HTTP_409_CONFLICT, "Hire at least one employee first.")

    model_name = request.app.state.settings.staffroom_model
    team = build_team(employees, model=partial(chat_model, model_name))
    return await team.run(body.goal)
