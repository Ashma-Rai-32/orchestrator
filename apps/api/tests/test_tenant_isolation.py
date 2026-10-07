"""Proof that Postgres row-level security isolates tenants for the API's role.

Data is seeded as the owner (a superuser here, so it bypasses RLS); every
assertion runs as `staffroom_app`, the role the API uses.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from staffroom_api.db.tenancy import tenant_transaction

pytestmark = pytest.mark.anyio

ACME, GLOBEX = uuid.uuid4(), uuid.uuid4()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module", autouse=True)
def seed(rls_db: dict[str, str]) -> None:
    engine = create_engine(rls_db["owner"])
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenants (id, name) VALUES (:a, 'Acme'), (:g, 'Globex')"),
            {"a": ACME, "g": GLOBEX},
        )
        conn.execute(
            text(
                "INSERT INTO employees (tenant_id, name, skills) VALUES "
                "(:a, 'Robin', '{react}'), (:a, 'Sam', '{node}'), (:g, 'Kim', '{react}')"
            ),
            {"a": ACME, "g": GLOBEX},
        )
    engine.dispose()


@pytest.fixture
async def app_engine(rls_db: dict[str, str]) -> AsyncIterator[AsyncEngine]:
    # pool_size=1: every transaction reuses the same connection, to catch leaks.
    engine = create_async_engine(rls_db["app"], pool_size=1, max_overflow=0)
    yield engine
    await engine.dispose()


async def employee_names(engine: AsyncEngine, tenant_id: uuid.UUID) -> list[str]:
    async with tenant_transaction(engine, tenant_id) as conn:
        rows = await conn.execute(text("SELECT name FROM employees ORDER BY name"))
        return list(rows.scalars())


async def test_each_tenant_sees_only_its_own_rows(app_engine: AsyncEngine) -> None:
    assert await employee_names(app_engine, ACME) == ["Robin", "Sam"]
    assert await employee_names(app_engine, GLOBEX) == ["Kim"]

    async with tenant_transaction(app_engine, ACME) as conn:
        tenants = (await conn.execute(text("SELECT name FROM tenants"))).scalars().all()
    assert tenants == ["Acme"]


async def test_no_tenant_set_sees_nothing(app_engine: AsyncEngine) -> None:
    async with app_engine.begin() as conn:
        rows = (await conn.execute(text("SELECT name FROM employees"))).all()
    assert rows == []


async def test_tenant_setting_does_not_leak_to_next_transaction(app_engine: AsyncEngine) -> None:
    assert await employee_names(app_engine, ACME) == ["Robin", "Sam"]
    async with app_engine.begin() as conn:  # same pooled connection, no tenant set
        rows = (await conn.execute(text("SELECT name FROM employees"))).all()
    assert rows == []


async def test_cannot_insert_rows_for_another_tenant(app_engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        async with tenant_transaction(app_engine, ACME) as conn:
            await conn.execute(
                text("INSERT INTO employees (tenant_id, name, skills) VALUES (:g, 'Spy', '{}')"),
                {"g": GLOBEX},
            )


async def test_cannot_update_or_delete_another_tenants_rows(app_engine: AsyncEngine) -> None:
    async with tenant_transaction(app_engine, ACME) as conn:
        updated = await conn.execute(text("UPDATE employees SET name = 'x' WHERE name = 'Kim'"))
        deleted = await conn.execute(text("DELETE FROM employees WHERE name = 'Kim'"))
    assert updated.rowcount == 0
    assert deleted.rowcount == 0
    assert await employee_names(app_engine, GLOBEX) == ["Kim"]


async def test_cannot_move_own_row_to_another_tenant(app_engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        async with tenant_transaction(app_engine, ACME) as conn:
            await conn.execute(
                text("UPDATE employees SET tenant_id = :g WHERE name = 'Robin'"), {"g": GLOBEX}
            )


def test_every_tenant_table_has_rls(rls_db: dict[str, str]) -> None:
    """Guard for new tables: anything with a tenant column must be under RLS."""
    engine = create_engine(rls_db["owner"])
    with engine.connect() as conn:
        unprotected = (
            conn.execute(
                text("""
                SELECT c.relname FROM pg_class c
                JOIN information_schema.columns col
                  ON col.table_name = c.relname AND col.column_name = 'tenant_id'
                WHERE col.table_schema = 'public'
                  AND NOT (c.relrowsecurity AND c.relforcerowsecurity
                           AND EXISTS (SELECT 1 FROM pg_policies p WHERE p.tablename = c.relname))
            """)
            )
            .scalars()
            .all()
        )
    engine.dispose()
    assert unprotected == []


async def test_app_role_cannot_switch_off_rls(app_engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError, match="must be owner"):
        async with app_engine.begin() as conn:
            await conn.execute(text("ALTER TABLE employees DISABLE ROW LEVEL SECURITY"))
