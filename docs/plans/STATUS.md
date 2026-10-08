# Status

_Last updated: 2026-10-07_

## Current milestone

**M-1 Framework discovery**, in small increments (one concept per step, run and shown, maintainer reviews and commits).

## Next step

M-1 trimmed (2026-10-07, maintainer: "get to the actual implementation"). Only spikes that change architecture remain; other frameworks are learned in the milestone that first uses them.

- [x] Spike `langchain-models` → [docs/frameworks/langchain-models.md](../frameworks/langchain-models.md) (verdict: adopt behind one adapter).
- [x] Spike `langgraph-core`: StateGraph, reducers, runtime context, v2 streaming, conditional edges, `Send` fan-out/fan-in.
- [x] Spike `team-builder` → ADR-0007 (tool-calling coordinator, one tool per skill pool).
- [x] Spike `checkpoint-interrupt`: pause in one process, resume in another via `PostgresSaver`; `response_schema` validates admin answers. Findings: [docs/frameworks/langgraph.md](../frameworks/langgraph.md).
- [x] M0: FastAPI + `/health` in compose; Alembic (migrate job before API); tenants + employees; RLS with non-owner app role (ADR-0005), 7 isolation tests.
- [ ] **M0 remaining**: auth (ADR-0003, revisit Zitadel weight), task queue ADR-0004, observability ADR-0006.
- [x] M1: skill catalog + employees API; team builder (ADR-0007) with rule-based fake; runs + events (RLS); WebSocket via Redis Streams; Taskiq worker (ADR-0004); resume from LangGraph Postgres checkpoint (checkpoint tables under RLS by thread_id prefix). Crash demo verified: resumed run re-ran only the summary step.
- [x] taskiq-redis reclaim bug fixed with `broker.py` subclass (option a); verified live. Upstream issue drafted for the maintainer to file.
- [ ] M5: domain watchdog for runs stuck in `running` (option c) — also covers segment timeouts.
- [ ] Known gap: a segment that times out (taskiq `timeout`) is cancelled with `CancelledError` (not caught) → run stays `running`. Handle with the watchdog/fix above.
- [x] Auth (ADR-0003): Keycloak organizations = tenants, realm as code; API verifies tokens with PyJWT; WebSocket token via subprotocol. Header stub removed.
- [x] M2: hardened Docker sandbox per run (ADR-0006), deepagents FilesystemMiddleware tools for employees, Playwright MCP inside the sandbox (docs/frameworks/playwright-mcp.md).
- [x] M2: skill catalog `tools` → toolsets (`agents/toolsets.py`); Testing skill gets the browser; live run verified (builders build, tester checks in Chromium).
- [x] M3: office UI (Phaser 4, Vite, Tiled map + desk spots, generated placeholder art), Keycloak sign-in via oidc-client-ts, live run visualisation over WebSocket. Verified in a real browser.
- [x] M4a: Langfuse tracing (ADR-0008); verified live, incl. secret masking (a leak in framework objects was found and fixed).
- [x] M4b (mostly): real models via Ollama (slow locally) and Gemini free tier; 6 robustness bugs found by real runs and fixed; Gemini built a real landing page. Free tier = 20 requests/day per model → main model gemini-3.5-flash-lite + ModelFallbackMiddleware chain across free models.
- [x] M6.1 inbox: `ask_admin` tool → LangGraph interrupt; employees inherit the checkpointer (experiment: with False the answer never arrived); run status `waiting`; `inbox_items` (RLS); `GET /inbox`, `POST /inbox/{id}/answer` resumes once all questions are answered; office inbox panel + "?" bubbles. Verified in a real browser.
- Fixed on the way: GraphInterrupt swallowed by the failed-task handler (re-raise GraphBubbleUp); runs stuck `queued` on setup errors; Alembic autogenerate wanted to DROP the checkpoint tables (include_object filter + test); labels not following walking characters (Phaser Container).
- [x] M6.2a/b: OpenBao secret store (ADR-0009, dev mode in compose); `ask_admin(secret_name=...)`; inbox password field; value goes to OpenBao only. Verified live: value in OpenBao, 0 occurrences in a full Postgres dump and in Redis streams.
- [x] M6.2c: tenant secrets as per-command env vars in the sandbox; values masked in command output and downloads (limits in ADR-0009).
- [ ] **Next: M6.3 deploy with approval** (preview → admin approves → publish), then M7 evals.
- Office polish backlog adds: overlapping bubbles at the huddle.
- [ ] Secrets: inbox form → secret store; agents get secret names only (also covers secrets typed into goals).
- [ ] Office polish backlog (deferred by maintainer, 2026-10-07: "do it later"): real CC0 art (Kenney; isometric option), pathfinding, character variants, inbox panel, hire UI. Decision: stay 2D; no 3D.
- Learned: use `message.text` (not `str(content)`): MCP tools and real models return content-block lists; `.text` is a `TextAccessor` str subclass in langchain-core 1.6.
- [ ] Deferred until the maintainer has a key: E2B backend behind `SANDBOX_BACKEND=e2b` (check langchain-e2b vs deepagents 0.7 pin).
- [ ] Remaining M0 ADR: observability (Langfuse wiring) — next free ADR number.

Moved out of M-1: Langfuse → M0/M1, MCP + Playwright → M2, Agent Server → ADR from docs.

## Answered questions

The maintainer said "proceed" without picking options, so the recommendations were adopted. Any of these can still be overridden.

| # | Question | Adopted |
|---|---|---|
| Q1 | LangGraph Agent Server vs own FastAPI | Own FastAPI on MIT `langgraph`; `langgraph-server` spike in M-1 → ADR-0008 |
| Q2 | Auth provider | Zitadel (self-hosted). **Revisit in ADR-0003:** Zitadel v4 compose is 4 containers (Traefik, API, Next.js login, Postgres); added to compose only at the M0 auth task |
| Q3 | Real LLM in spikes | Fake model in CI; real-model run opt-in via `STAFFROOM_REAL_MODEL=1` (needs a key from maintainer) |
| Q4 | 10 same-skill employees: pool or personas | Spike tests both; default decided in ADR-0007 |
| Q5 | Push / license | No pushing by agents; license MIT |

## Versions checked (PyPI/npm/GitHub, 2026-10-07)

Python libs: langgraph 1.2.14 · langchain 1.4.3 · langchain-core 1.6.7 · langgraph-supervisor 0.0.31 · langgraph-swarm 0.1.0 · langgraph-checkpoint-postgres 3.1.2 · langchain-mcp-adapters 0.3.2 · langfuse 4.17.0 · playwright 1.63.0 · celery 5.6.3 · dramatiq 2.2.1 · arq 0.28.0 · taskiq 0.13.0 · fastapi-users 15.0.5

Tooling: uv 0.12.23 · ruff 0.16.10 · mypy 2.4.0 · pytest 9.1.1 · pre-commit 4.6.2 · gitleaks 8.30.1 · phaser 4.2.1

Services: Langfuse server v4 (`langfuse/langfuse:4`) · Zitadel v4.19.4 · Postgres 17 · Redis 7.4

CI actions: actions/checkout v7 · astral-sh/setup-uv v10 · actions/cache v6 · gitleaks/gitleaks-action v3

## Flags to verify in docs (from planning, not yet confirmed)

- `langgraph-supervisor` / `langgraph-swarm` are pre-1.0; LangChain docs may now recommend a hand-built tool-calling supervisor via `langchain.agents.create_agent`.
- `langgraph.prebuilt.create_react_agent` superseded by `langchain.agents.create_agent` + middleware in v1.
- Playwright has an official MCP server → reach via `langchain-mcp-adapters` instead of writing tool wrappers.
- Langfuse v4 SDK is OTel-native.
- arq possibly maintenance-only.
- Fake chat models may lack `bind_tools` → may need a tiny subclass.

## Known risks

- LangGraph checkpointer/store tables have no tenant column → isolation via `thread_id`/store namespace prefixed by tenant, enforced in one place, tested.
- Postgres RLS is bypassed by the table owner → app connects as a non-owner role (or `FORCE ROW LEVEL SECURITY`); tests use the app role.
- Secrets: agents reference secrets by name; tools resolve at call time; Langfuse masking as second layer.
- Runaway autonomous runs → recursion limit + per-run budget via middleware.
- Local stack is heavy (Langfuse = 6 containers, Zitadel = 4) → both behind profiles.

## Decision log

| Date | Decision | Where |
|---|---|---|
| 2026-10-07 | Plans live in `docs/plans/` (STATUS + roadmap) | this file |
| 2026-10-07 | Agents never commit; maintainer commits | `docs/plans/README.md`, `CLAUDE.md` |
| 2026-10-07 | ADRs use trimmed MADR | ADR-0001 |
| 2026-10-07 | Monorepo, virtual uv workspace, spikes as PEP 723 scripts | ADR-0002 |
| 2026-10-07 | Langfuse vendored from upstream compose into `infra/compose/langfuse.yaml`, profile `observability`, generic env vars namespaced `LANGFUSE_*` | compose header comment |
| 2026-10-07 | CI: pre-commit (ruff, hygiene), gitleaks full-history job, compose config check; pytest job added with M0 code | `.github/workflows/ci.yml` |

## Gotchas found

- Langfuse upstream compose reads generic `REDIS_PORT`, `AWS_*`, `DATABASE_URL` → collided with Staffroom's `.env`. Fixed by namespacing.
- `langfuse-web` has no healthcheck, so `docker compose up --wait` returns before it is ready (~1 min to migrate on first start).
- Maintainer's machine runs a Homebrew Redis on 6379 → local `.env` uses `REDIS_PORT=6380`.
- uv not installed on maintainer's machine (`brew install uv`); `uv.lock` was generated with a temporary uv 0.12.23.

## Done

- [x] Initial plan proposed (M-1, M0, M1)
- [x] `docs/plans/` created
- [x] Scaffold: layout, CLAUDE.md, README, ADR-0001/0002, compose (verified: Postgres, Redis, Langfuse healthy, init API keys work), CI + pre-commit (passes locally)
