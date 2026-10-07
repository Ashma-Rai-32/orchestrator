# Langfuse (SDK 4.17.0, server v4 self-hosted, checked 2026-10-07)

Code: `apps/api/src/staffroom_api/observability.py`; decision: [ADR-0008](../adr/0008-observability-langfuse.md).

## What it can do

- **LangChain/LangGraph tracing with one callback**: `CallbackHandler()` in the run config traces every nested chain, model call (as GENERATION) and tool call (as TOOL), including subagents invoked inside tools.
- **Trace attributes**: `propagate_attributes(session_id, user_id, tags, trace_name)` stamps every span created inside it.
- **Masking**: `Langfuse(mask=fn)` runs `fn(data=...)` on inputs/outputs before export.
- OpenTelemetry under the hood; datasets, experiments, scores and prompt management for later evals (M7).

## What it cannot do

- Masking is per payload with your own rules; it has no built-in secret detection.
- The v4 server's public API no longer serves `/api/public/traces` ("events only" mode).

## Gotchas

- `LANGFUSE_HOST` is deprecated; use `LANGFUSE_BASE_URL` (or `base_url=`).
- The client is a process-wide singleton: create `Langfuse(...)` once at startup; `CallbackHandler()` uses it.
- **Mask functions see framework objects** (LangChain messages, LangGraph updates), not only dicts/strings; they are serialized *after* masking. Serialize first (we use Langfuse's `EventSerializer`), then redact. A live check caught this leak.
- Read traces via `/api/public/v2/observations?sessionId=…`.
- Unknown model classes (our fake) log "not able to parse the LLM model"; harmless.
- Call `get_client().shutdown()` on worker shutdown to flush.

## Verdict: adopt
