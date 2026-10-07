# Status

_Last updated: 2026-10-07_

## Current milestone

**Pre-M-1: planning.** Plan proposed, awaiting answers to open questions before scaffolding.

## Next step

1. Get answers to the open questions below (or "go with recommendations").
2. Scaffold, one commit each: repo layout → CLAUDE.md → README skeleton → ADR-0001, ADR-0002 → docker compose → CI.
3. Start M-1 spikes (see [roadmap.md](roadmap.md#m-1-framework-discovery)).

## Open questions

| # | Question | Recommendation |
|---|---|---|
| Q1 | Self-host LangGraph Agent Server (`langgraph-api`: threads, background runs, cron, streaming, store) or own FastAPI + task queue on the MIT `langgraph` library? | Own FastAPI (full control of RLS/auth, more CV value); still run a `langgraph-server` spike and decide in ADR-0008. Check self-hosted licensing. |
| Q2 | Auth provider? Zitadel (self-hosted, orgs = tenants) / Keycloak (heavier) / Clerk or WorkOS (hosted, breaks 5-min local run) / fastapi-users (no orgs) | Zitadel in compose + authlib JWT verification |
| Q3 | Real-LLM key + small budget for M-1 spikes? | Fake model in CI; one real-model run per spike behind an env flag |
| Q4 | 10 same-skill employees: interchangeable pool or distinct personas? | Product call; spike tests both (role routing + `Send` pool vs. N handoff targets) |
| Q5 | Create public GitHub repo / push? License MIT or Apache-2.0? | Remote `origin` already exists; confirm push permission and license |

## Versions checked (PyPI/npm, 2026-10-07)

langgraph 1.2.14 · langchain 1.4.3 · langchain-core 1.6.7 · langgraph-supervisor 0.0.31 · langgraph-swarm 0.1.0 · langgraph-checkpoint-postgres 3.1.2 · langchain-mcp-adapters 0.3.2 · langfuse 4.17.0 · playwright 1.63.0 · phaser 4.2.1 · celery 5.6.3 · dramatiq 2.2.1 · arq 0.28.0 · taskiq 0.13.0 · fastapi-users 15.0.5

## Flags to verify in docs (from planning, not yet confirmed)

- `langgraph-supervisor` / `langgraph-swarm` are pre-1.0; LangChain docs may now recommend a hand-built tool-calling supervisor via `langchain.agents.create_agent`.
- `langgraph.prebuilt.create_react_agent` superseded by `langchain.agents.create_agent` + middleware in v1.
- Playwright has an official MCP server → reach via `langchain-mcp-adapters` instead of writing tool wrappers.
- Langfuse v4 SDK is OTel-native; self-host v3 server needs ClickHouse + MinIO + Redis + Postgres → put behind compose profile `observability`.
- arq possibly maintenance-only.
- Fake chat models may lack `bind_tools` → may need a tiny subclass.

## Known risks

- LangGraph checkpointer/store tables have no tenant column → isolation via `thread_id`/store namespace prefixed by tenant, enforced in one place, tested.
- Postgres RLS is bypassed by the table owner → app connects as a non-owner role (or `FORCE ROW LEVEL SECURITY`); tests use the app role.
- Secrets: agents reference secrets by name; tools resolve at call time; Langfuse masking as second layer.
- Runaway autonomous runs → recursion limit + per-run budget via middleware.

## Decision log

| Date | Decision | Where |
|---|---|---|
| 2026-10-07 | Plans live in `docs/plans/` (STATUS + roadmap) | this file |

## Done

- [x] Initial plan proposed (M-1, M0, M1)
- [x] `docs/plans/` created
