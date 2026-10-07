import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from staffroom_api.db.models import Employee
from staffroom_api.deps import TenantId, TenantSession
from staffroom_api.skills.catalog import UnknownSkillError, merge_skills

router = APIRouter(tags=["employees"])


class EmployeeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    skills: list[str] = Field(min_length=1)


class EmployeeOut(BaseModel):
    id: uuid.UUID
    name: str
    skills: list[str]
    created_at: datetime


def _out(e: Employee) -> EmployeeOut:
    return EmployeeOut(id=e.id, name=e.name, skills=e.skills, created_at=e.created_at)


@router.post("/employees", status_code=status.HTTP_201_CREATED)
async def hire_employee(
    body: EmployeeCreate, session: TenantSession, tenant_id: TenantId
) -> EmployeeOut:
    try:
        merged = merge_skills(body.skills)
    except UnknownSkillError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e

    employee = Employee(tenant_id=tenant_id, name=body.name, skills=list(merged.skill_keys))
    session.add(employee)
    await session.flush()
    await session.refresh(employee)
    return _out(employee)


@router.get("/employees")
async def list_employees(session: TenantSession) -> list[EmployeeOut]:
    # No tenant filter here on purpose: row-level security does it.
    rows = await session.scalars(select(Employee).order_by(Employee.created_at))
    return [_out(e) for e in rows]
