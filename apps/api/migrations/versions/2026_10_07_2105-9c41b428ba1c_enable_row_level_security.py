"""enable row level security

Tenant isolation enforced by Postgres, not by application WHERE clauses.
See docs/adr/0005-tenant-isolation-with-postgres-rls.md.

- `staffroom_app` is the role the API connects as. It does not own the tables,
  so RLS applies to it. Infra creates it with LOGIN and a password (compose init
  script / Terraform); this migration only creates it NOLOGIN if missing, so
  migrations also work on a bare database (tests).
- The API sets `app.tenant_id` per transaction (`set_config(..., true)`).
  Unset or empty -> `app_current_tenant()` is NULL -> no rows match.

Hand-written: Alembic autogenerate does not track roles, grants or policies.

Revision ID: 9c41b428ba1c
Revises: dd7ba644cf13
Create Date: 2026-10-07 21:05:13.111674

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c41b428ba1c"
down_revision: str | Sequence[str] | None = "dd7ba644cf13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "staffroom_app"

# table -> column that holds the tenant id
TENANT_TABLES = {"tenants": "id", "employees": "tenant_id"}


def upgrade() -> None:
    op.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN;
            END IF;
        END $$
    """)
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")

    # NULLIF: once set in a session, an unset custom setting reads as '' not NULL,
    # and ''::uuid would raise instead of matching nothing.
    op.execute("""
        CREATE FUNCTION app_current_tenant() RETURNS uuid
        LANGUAGE sql STABLE
        AS $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$
    """)

    for table, column in TENANT_TABLES.items():
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE: applies to the table owner too (superusers still bypass).
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        # USING filters reads/updates/deletes; WITH CHECK blocks writing other tenants' rows.
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING ({column} = app_current_tenant())
            WITH CHECK ({column} = app_current_tenant())
        """)


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.execute("DROP FUNCTION app_current_tenant()")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    # The role itself is left in place: roles are cluster-wide and owned by infra.
