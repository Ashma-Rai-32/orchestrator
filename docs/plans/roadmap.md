# Roadmap

Each task lists **files**, the **framework** doing the work, and the **custom** code that remains. Status lives in [STATUS.md](STATUS.md).

## Scaffold (after open questions are answered)

One commit each:

1. `chore: init repo layout` — `apps/api/ apps/office/ packages/schemas/ sandbox/ infra/ experiments/ spikes/ docs/adr/ docs/frameworks/`, `.gitignore`, `LICENSE`
2. `docs: add CLAUDE.md`
3. `docs: add README skeleton` — Mermaid architecture, real-vs-stubbed status table, 5-minute run guide
4. `docs(adr): 0001 record architecture decisions (MADR)`, `docs(adr): 0002 monorepo with uv workspace`
5. `build: add docker compose`
6. `ci: add GitHub Actions workflow`

## M-1 Framework discovery

Per spike: `spikes/<name>/main.py` (PEP 723 inline deps, run with `uv run`), `test_spike.py` (fake model), `README.md`; plus `docs/frameworks/<name>.md` with sections **Can / Cannot / Gotchas / Verdict (adopt|skip)**.

| Spike | Explores | Custom |
|---|---|---|
| `langchain-models` | `init_chat_model` across Anthropic/Bedrock/Gemini from config; `bind_tools`, `with_structured_output`, `with_fallbacks`, `InMemoryRateLimiter`; `GenericFakeChatModel` / `FakeMessagesListChatModel` | config dict |
| `langgraph-core` | `StateGraph`, reducers, `Send` fan-out, subgraphs, stream modes, `get_stream_writer`, recursion limit, `create_agent` + middleware | toy graph |
| `langgraph-supervisor` | **Team built at runtime from employee records incl. 10 sharing the same skills.** Compare (a) `create_supervisor`, (b) hand-built tool-calling supervisor via `create_agent`, (c) role routing + `Send` worker pool. Measure tool count, prompt size, routing behaviour. | record→agent mapping |
| `langgraph-swarm` | `create_swarm`, handoff tools, `active_agent`; when peer handoff beats a coordinator | none |
| `checkpoint-interrupt` | **`interrupt()` → `Command(resume=…)`**; `AsyncPostgresSaver`; kill process mid-run and resume from another; `get_state_history`; `PostgresStore` namespaced `(tenant, employee)`; `HumanInTheLoopMiddleware` | none |
| `mcp-adapters` | `MultiServerMCPClient` over stdio + streamable HTTP; toy FastMCP server | ~10-line server |
| `playwright-tool` | Playwright MCP via adapters vs `PlayWrightBrowserToolkit` vs pytest-playwright, against a static fixture site | fixture site |
| `langfuse` | Official self-host compose, LangChain `CallbackHandler`, OTel spans, masking, sessions = run, user = tenant | masking regex |
| `langgraph-server` (if Q1) | threads, background runs, streaming vs. our planned stack | none |

Exit: `docs/frameworks/README.md` comparison matrix; ADR-0007 multi-agent topology; ADR-0008 Agent Server vs own API.

## M0 Foundations

| Files | Framework | Custom |
|---|---|---|
| root `pyproject.toml` (uv workspace), `.python-version`, `.pre-commit-config.yaml`, `.editorconfig`, ruff/mypy config | uv, ruff, mypy, pre-commit | config |
| `compose.yaml` — Postgres, Redis default; Langfuse (official compose) under profile `observability`; auth provider service | Docker Compose | YAML |
| `.github/workflows/ci.yml` — setup-uv, ruff, mypy, pytest with Postgres/Redis services; office: `npm ci`, `tsc`, `vite build` | GitHub Actions | YAML |
| `apps/api/src/staffroom_api/main.py`, `settings.py` | FastAPI, pydantic-settings | app factory |
| `routes/health.py` (DB + Redis checks) | FastAPI | ~20 lines |
| `db/session.py` | SQLAlchemy 2 async + asyncpg | none |
| `db/tenancy.py` — `SET LOCAL app.tenant_id` per transaction | SQLAlchemy events | **~30 lines (no maintained lib)** |
| `models/tenant.py`, `auth.py` (OIDC/JWT verify per Q2) | SQLAlchemy, authlib | thin glue |
| `apps/api/alembic/` — 0001 tenants, users, RLS policies, non-owner app role | Alembic (async template) | policy SQL |
| `apps/api/tests/test_rls_isolation.py` — A can't read/write B; no tenant set → zero rows | pytest, testcontainers-python | tests |
| `packages/schemas/` — shared Pydantic v2 models; TS types via `openapi-typescript` | Pydantic, openapi-typescript | models |
| `apps/office/` — Vite vanilla-ts + empty Phaser 4 scene (CI coverage only) | Vite, Phaser | none |

ADRs: 0003 auth · 0004 task queue (Celery vs Dramatiq vs arq vs taskiq) · 0005 RLS tenancy · 0006 observability.

## M1 Agent core

| Files | Framework | Custom |
|---|---|---|
| `packages/schemas/{skill,employee,events}.py` — events as discriminated union on `type` | Pydantic | models |
| models + migration 0002: skills, employees, employee_skills, goals, runs, events (all RLS) | SQLAlchemy, Alembic | schema |
| `agents/ports.py` — `ModelFactory`, `TeamBuilder`, `EventSink` Protocols | — | small interfaces (swap-ability) |
| `agents/models.py` — the single provider adapter + fake model | `init_chat_model` | config mapping |
| `agents/skills/registry.py` — catalog (prompt fragment + tool names), skill merge | — | **product logic** |
| `agents/team_builder.py` — DB rows → `create_agent` per employee → coordinator graph (per ADR-0007) | LangGraph/LangChain | mapping |
| `agents/prompts/coordinator.md` | — | prompt |
| `agents/events.py` — LangGraph `astream(stream_mode=[...], subgraphs=True)` → domain events | LangGraph streaming | **one mapping function** |
| `routes/goals.py`, `worker/tasks.py` — enqueue, run graph with `AsyncPostgresSaver`, `thread_id = tenant:run` | task queue (ADR-0004), LangGraph checkpointer | glue |
| `routes/ws.py` — WebSocket fed from Redis Streams (resume from last event id); events also persisted | FastAPI, redis-py | glue |
| tests: `test_team_builder.py` (10 identical), `test_goal_run_fake_model.py` (event snapshot), `test_ws_stream.py`, `test_events_tenant_isolation.py` | pytest | tests |

## Later milestones (outline only; detail when reached)

- **M2 Sandbox and tools** — ADR: Docker SDK with strict limits vs hosted sandbox (E2B, Daytona, Modal). No custom isolation logic. Playwright tool wired in.
- **M3 Office UI** — Phaser 4, Tiled tilemaps, agents as sprites driven by WS events, inbox UI.
- **M4 Real models** — one end-to-end run on a real provider.
- **M5 Durability** — survive worker restart / admin logout via checkpointer.
- **M6 Deploy with admin approval** — interrupt-gated publish.
- **M7 Research harness** — org configs, benchmark briefs, experiment runner, trace analysis (Langfuse).
