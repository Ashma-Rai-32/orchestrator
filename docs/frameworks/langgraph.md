# LangGraph + LangChain agents (langgraph 1.2.14, langchain 1.4.3, langgraph-checkpoint-postgres 3.1.2, checked 2026-10-07)

Spikes: [langgraph-core](../../spikes/langgraph-core/), [team-builder](../../spikes/team-builder/), [checkpoint-interrupt](../../spikes/checkpoint-interrupt/). Findings from running them and from the installed source.

## What it can do

- **StateGraph**: nodes return partial updates; per-key reducers (`Annotated[list, operator.add]`) decide replace vs merge.
- **Run context**: `context_schema` + `Runtime[Ctx]` give nodes immutable run-scoped data (tenant id, db handles) that is never checkpointed.
- **Streaming v2**: `stream(..., version="v2")` yields typed parts `{type, ns, data}` for `updates`, `values`, `messages`, `custom`, `checkpoints`, `tasks`, `debug`. `ns` identifies subgraphs / named subagents.
- **Routing and parallelism**: `add_conditional_edges` for branching; returning a list of `Send` runs one node N times in parallel with private inputs; the next step waits for all (fan-in for free). Parallel writes are applied in deterministic task order.
- **Agents**: `langchain.agents.create_agent(model, tools, system_prompt, middleware, name, checkpointer, ...)` is the agent loop. Multiple tool calls in one turn run in parallel. Middleware: `ModelCallLimitMiddleware`, `ModelRetryMiddleware`, `ModelFallbackMiddleware`, `ToolCallLimitMiddleware`, `ToolRetryMiddleware`, `HumanInTheLoopMiddleware`, `PIIMiddleware`, `SummarizationMiddleware` and more.
- **Durable pause/resume**: `interrupt(value, response_schema=Model)` pauses a node; with `PostgresSaver` the state survives process exit; `graph.stream(Command(resume=...), {"configurable": {"thread_id": ...}})` from any process continues. `response_schema` (Pydantic) emits a JSON Schema for the client form **and** validates the resume value.
- **History**: `get_state_history` lists every checkpoint (time travel / audit).
- **Visualisation**: `graph.get_graph().draw_mermaid()`.

## What it cannot do

- Checkpoint tables have no tenant column. Isolation must come from tenant-prefixed `thread_id`s (and store namespaces), enforced in our code.
- An invalid resume value raises inside the node (`ValidationError`); the run stays paused, but the API must validate against `response_schema` **before** calling resume to return a clean 4xx.
- No built-in "which employee in a pool is free" scheduling; that is product logic.

## Gotchas

- **A resumed node re-runs from its first line.** Side effects before `interrupt()` happen twice. Put interrupts first, or in their own node. (Only the interrupted node re-runs; earlier nodes do not.)
- `config_schema` is deprecated (removed in 2.0); use `context_schema`.
- `stream()` defaults to `version="v1"`; pass `"v2"` explicitly.
- `add_conditional_edges` without a return type hint or `path_map` draws edges to every node.
- `PostgresSaver.setup()` must be called once (idempotent); in the app it belongs in startup/migrations, not per request.
- `langgraph.prebuilt.create_react_agent` is superseded by `langchain.agents.create_agent`.

## Verdict: adopt, behind the team-builder interface

- Topology: tool-calling coordinator with skill pools ([ADR-0007](../adr/0007-multi-agent-topology.md)).
- **langgraph-supervisor: skip.** Its README recommends the tool-calling pattern instead.
- **langgraph-swarm: skip.** Peer handoffs without a central planner conflict with the product's platform coordinator.
- Durability: `AsyncPostgresSaver` in the app, `thread_id = f"{tenant_id}:{run_id}"`.
- Admin inbox = pending interrupts; form rendered from `response_schema`; answers carry secret **names**, never secret values.
