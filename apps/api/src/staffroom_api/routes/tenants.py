import uuid
from datetime import datetime

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from staffroom_api.db.models import Tenant
from staffroom_api.db.tenancy import tenant_transaction

router = APIRouter(tags=["tenants"])


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime


@router.post("/tenants", status_code=status.HTTP_201_CREATED)
async def create_tenant(body: TenantCreate, request: Request) -> TenantOut:
    """STUB sign-up until auth lands: anyone can create a tenant.

    RLS only allows writing the row whose id is the current tenant, so the id
    is chosen here and set as the tenant for this one transaction.
    """
    tenant_id = uuid.uuid4()
    async with tenant_transaction(request.app.state.db, tenant_id) as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        tenant = Tenant(id=tenant_id, name=body.name)
        session.add(tenant)
        await session.flush()
        await session.refresh(tenant)  # load server defaults (created_at)
    return TenantOut(id=tenant.id, name=tenant.name, created_at=tenant.created_at)
