# 0008. Observability: self-hosted Langfuse via its LangChain callback (OpenTelemetry)

- Status: accepted
- Date: 2026-10-07

## Context and problem

Agent runs are long, nested (coordinator → delegation tools → employee agents → sandbox and browser tools) and soon cost real money. We need to see every model call, tool call, latency and token count per run and per tenant, without secrets leaking into the tracing backend. The brief names Langfuse (self-hosted) and OpenTelemetry.

## Decision drivers

- Zero custom instrumentation: hook into the framework we already use.
- Run and tenant visible on every trace; self-hosted, keyless local stack.
- Secrets never exported, even if a model or tool echoes one.

## Options considered

1. **Langfuse v4 SDK (4.17.0) + `langfuse.langchain.CallbackHandler`**: OpenTelemetry-based; one handler on the LangGraph run config traces everything nested; `propagate_attributes` stamps session/user/tags; `mask` hook before export.
2. **Raw OpenTelemetry + LangChain/LangGraph OTel instrumentation + a generic backend (Jaeger/Tempo)**: vendor neutral, but no LLM-specific views (prompts, token costs, sessions) without building them.
3. **LangSmith**: first-party for LangChain, but hosted (self-hosting is enterprise-only).

## Decision

Option 1.

- `staffroom_api/observability.py`: `init_tracing` (worker startup; off unless keys are set), `run_tracing(tenant, run)` → `propagate_attributes(trace_name="run", session_id=run, user_id=tenant)` and a `CallbackHandler` passed in the coordinator's run config. Employee runs inherit it through the run context.
- One run = one Langfuse **session**, one tenant = one Langfuse **user**.
- `redact` is the Langfuse `mask`: regexes for JWTs, `sk-`-style keys, AWS key ids, `Bearer …`, `key=value` secrets. Non-plain objects are first serialized with Langfuse's own `EventSerializer`, then redacted.

## Consequences

- Good: verified live: one run → one trace with ~50–80 nested observations (model calls, delegations, `write_file`/`execute`, browser tools), tagged with the tenant.
- Good: verified live that a fake key typed into a goal does not reach Langfuse (0 occurrences, masked everywhere).
- Gotcha (fixed): masking only plain dicts/strings leaked secrets inside LangChain message objects in LangGraph outputs; caught by the live check, covered by a test.
- Gotcha: Langfuse v4 servers run "events only"; `/api/public/traces` is gone, use `/api/public/v2/observations`.
- Gotcha: `LANGFUSE_HOST` is deprecated in SDK v4; use `LANGFUSE_BASE_URL`.
- Bad: `EventSerializer` is imported from a private module (`langfuse._utils`); pinned version + test will catch breakage.
- Limit: masking protects traces only. A secret typed into a goal still reaches prompts, events and the UI. Follow-up: secrets entered through an inbox form into a secret store; agents receive names only.

## Sources

- Installed langfuse 4.17.0: `langchain/CallbackHandler.py`, `_client/client.py`, `_client/propagation.py`, `_client/environment_variables.py`, `api/observations/`.
- Self-hosted Langfuse v4 server (compose profile `observability`), queried 2026-10-07.
