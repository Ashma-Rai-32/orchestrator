# 0005. Tenant isolation with Postgres row-level security

- Status: accepted
- Date: 2026-10-07

## Context and problem

Staffroom is multi-tenant. A bug in one query (a missing `WHERE tenant_id = ...`) must not expose another tenant's employees, goals or secrets. Agents also run in background workers, where request-scoped filtering is easy to forget.

## Decision drivers

- Isolation enforced below the application, so one forgotten filter is not a breach.
- Provable with automated tests.
- Minimal custom code; works with SQLAlchemy async and connection pooling.

## Options considered

1. **Application-level filtering only** (every query adds `tenant_id`): simple, but one missed filter leaks data; not enforceable.
2. **Schema or database per tenant**: strong isolation, but migrations and connection pools multiply with tenant count.
3. **Postgres row-level security with a non-owner app role and a per-transaction tenant setting.**
4. **`alembic-utils` to manage policies in autogenerate**: last release 0.8.8 (April 2025), predates SQLAlchemy 2.1. Not adopted.

## Decision

Option 3.

- Migrations run as the owner role; the API connects as `staffroom_app`, which does not own tables, so RLS applies. Tables also use `FORCE ROW LEVEL SECURITY`.
- Policy on each tenant table: `USING` and `WITH CHECK` compare the tenant column with `app_current_tenant()`, which reads `app.tenant_id` (`NULLIF(..., '')`, so unset means no rows, not an error).
- The API sets the tenant with `set_config('app.tenant_id', ..., true)` at the start of each transaction (`db/tenancy.py`, about 10 lines). `true` makes it transaction-local, so pooled connections cannot leak a tenant.
- Roles and passwords are infrastructure (compose init script now, Terraform later). Migrations only grant privileges and create policies, in a hand-written migration (autogenerate does not track them).

## Consequences

- Good: forgetting a filter returns no rows instead of another tenant's rows. Seven tests in `tests/test_tenant_isolation.py` prove read, write, update, move and leak cases, plus that the app role cannot disable RLS.
- Bad: every new tenant table needs its policy added in a migration. Follow-up: a test that fails if any table with a `tenant_id` column lacks RLS.
- Bad: LangGraph checkpoint tables have no tenant column (see docs/frameworks/langgraph.md); they are isolated by tenant-prefixed `thread_id`s instead.

## Sources

- PostgreSQL 17 docs: Row Security Policies, `set_config`, `current_setting(name, missing_ok)`.
- alembic-utils 0.8.8 on PyPI (checked 2026-10-07).
