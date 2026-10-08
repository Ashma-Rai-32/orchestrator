# 0009. Tenant secrets in OpenBao

- Status: accepted (chosen by the maintainer)
- Date: 2026-10-08

## Context and problem

Employees get blocked on credentials ("I need an API key for the LLM provider"). The admin provides them through the inbox (M6.1). Non-negotiables: secrets never appear in prompts, logs, traces or events; agents reference secrets by **name**; tools resolve values only at execution time; tenants are isolated.

## Decision drivers

- A real secrets manager rather than hand-rolled key handling.
- Encryption at rest, versioning, audit trail.
- Open-source licence; keyless local run.
- Swappable behind a small interface (e.g. a managed cloud service in production).

## Options considered (checked 2026-10-08)

1. **HashiCorp Vault 2.1.2**: the reference product, but under the Business Source License (not open source).
2. **OpenBao 2.7.1** (Linux Foundation fork of Vault, MPL-2.0, released 2026-10-01): KV v2 (versioned), audit devices, policies, transit encryption; Vault-compatible API, so the `hvac` 2.4.0 client works. Dev mode needs no setup.
3. **Postgres + envelope encryption** (`cryptography` 50.0.2): no new service, reuses RLS isolation; we would own key handling, rotation and audit (about 40 lines of glue plus KMS in production).
4. **Infisical**: full secrets platform, mixed licence, heavy to self-host.
5. **AWS Secrets Manager**: managed, but needs AWS; good later production backend.

## Decision

Option 2, behind a `SecretStore` Protocol (`staffroom_api/secrets.py`).

- KV v2 mount `secret/`, path `tenants/<tenant_id>/<NAME>`; names are environment-variable style (`^[A-Z][A-Z0-9_]{1,63}$`) so they can be injected into the sandbox as env vars.
- Local: OpenBao **dev mode** in compose (in-memory, unsealed, fixed dev root token from `.env`).
- The API writes (inbox answers); the worker reads (sandbox injection, M6.2c). Agents, events, inbox rows and traces only ever carry the name.

## Consequences

- Good: real secrets manager semantics (versions, audit) with no custom crypto.
- Good: swapping to AWS Secrets Manager later is one class behind the Protocol.
- Bad: one more container. Dev mode keeps secrets **in memory**: they disappear when OpenBao restarts (fine locally, never for production).
- Bad: `hvac` is slow-moving (one release in two years); the Vault HTTP API it wraps is stable.
- Follow-ups (production): non-dev OpenBao with storage + auto-unseal, AppRole auth with per-service policies (API: write, worker: read) instead of a root token; enable an audit device.

## Sources

- GitHub: openbao/openbao v2.7.1, hashicorp/vault LICENSE (BSL), Infisical/infisical; PyPI: hvac 2.4.0, cryptography 50.0.2 (2026-10-08).
- `bao server -h` (dev mode flags) from the `openbao/openbao:2.7.1` image.
