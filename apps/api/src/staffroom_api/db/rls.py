"""SQL for putting a table under tenant row-level security (ADR-0005).

Used from migrations: `for sql in enable_tenant_rls("runs"): op.execute(sql)`.
Requires the `staffroom_app` role and `app_current_tenant()` from the first RLS migration.
"""

APP_ROLE = "staffroom_app"


def enable_tenant_rls(table: str, column: str = "tenant_id") -> list[str]:
    return [
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}",
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"""CREATE POLICY tenant_isolation ON {table}
            USING ({column} = app_current_tenant())
            WITH CHECK ({column} = app_current_tenant())""",
    ]


def disable_tenant_rls(table: str) -> list[str]:
    return [
        f"DROP POLICY tenant_isolation ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
        f"REVOKE ALL ON {table} FROM {APP_ROLE}",
    ]
