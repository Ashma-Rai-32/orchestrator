"""Request-scoped dependencies: who is the tenant, and a database session scoped to them."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from staffroom_api.db.tenancy import tenant_transaction


async def current_tenant(x_tenant_id: Annotated[uuid.UUID, Header()]) -> uuid.UUID:
    """STUB until auth lands: trusts an `X-Tenant-ID` header.

    Replaced by the tenant claim from a verified token (ADR-0003). Never expose
    the API publicly while this stub is in place.
    """
    return x_tenant_id


async def _tenant_session(
    request: Request, tenant_id: Annotated[uuid.UUID, Depends(current_tenant)]
) -> AsyncIterator[AsyncSession]:
    async with tenant_transaction(request.app.state.db, tenant_id) as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.flush()  # transaction commits when tenant_transaction exits


# scope="function": commit happens before the response is sent, so a 201 is never a lie.
TenantSession = Annotated[AsyncSession, Depends(_tenant_session, scope="function")]
TenantId = Annotated[uuid.UUID, Depends(current_tenant)]
