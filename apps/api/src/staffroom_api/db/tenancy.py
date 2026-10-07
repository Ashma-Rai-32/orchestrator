"""The one piece of tenancy glue: scope a database transaction to a tenant.

Postgres RLS policies read `app.tenant_id` (see the RLS migration). No maintained
library does this for SQLAlchemy; it is one `set_config` call.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine


@asynccontextmanager
async def tenant_transaction(
    engine: AsyncEngine, tenant_id: uuid.UUID
) -> AsyncIterator[AsyncConnection]:
    """Open a transaction in which RLS only exposes `tenant_id`'s rows.

    `is_local=true` scopes the setting to this transaction, so a pooled
    connection never carries one tenant's id into the next request.
    """
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        yield conn
