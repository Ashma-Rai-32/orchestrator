"""LangGraph Postgres checkpointer: schema setup, tenant isolation, per-run saver.

- The checkpointer owns and versions its own tables (`setup()`), so they are not
  in Alembic. The migrate job runs `python -m staffroom_api.agents.checkpoints`.
- Checkpoint tables have no tenant column. Thread ids are `<tenant_id>:<run_id>`,
  and RLS policies compare that prefix with `app_current_tenant()` (ADR-0005).
- Each run gets its own connection with `app.tenant_id` set for the whole session,
  so the framework's own queries are tenant-scoped too.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from staffroom_api.db.rls import APP_ROLE
from staffroom_api.settings import Settings

TENANT_SCOPED_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


def thread_id(tenant_id: uuid.UUID, run_id: uuid.UUID) -> str:
    return f"{tenant_id}:{run_id}"


def _psycopg_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@asynccontextmanager
async def run_checkpointer(
    settings: Settings, tenant_id: uuid.UUID
) -> AsyncIterator[AsyncPostgresSaver]:
    """A checkpointer on a dedicated connection pinned to one tenant."""
    async with await AsyncConnection.connect(
        _psycopg_url(settings.database_url),  # app role: RLS applies
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,  # all three required by AsyncPostgresSaver
    ) as conn:
        # is_local=false: session-wide, this connection serves only this tenant.
        await conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant_id),))
        yield AsyncPostgresSaver(conn)


async def setup(owner_url: str) -> None:
    """Create/upgrade checkpoint tables, then grant + isolate them. Idempotent."""
    async with AsyncPostgresSaver.from_conn_string(_psycopg_url(owner_url)) as saver:
        await saver.setup()
    async with await AsyncConnection.connect(_psycopg_url(owner_url), autocommit=True) as conn:
        for table in TENANT_SCOPED_TABLES:
            await conn.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
            await conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            await conn.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            await conn.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
            await conn.execute(f"""
                CREATE POLICY tenant_isolation ON {table}
                USING (split_part(thread_id, ':', 1) = app_current_tenant()::text)
                WITH CHECK (split_part(thread_id, ':', 1) = app_current_tenant()::text)
            """)


if __name__ == "__main__":
    asyncio.run(setup(Settings().migration_database_url))
    print("checkpoint tables ready")
