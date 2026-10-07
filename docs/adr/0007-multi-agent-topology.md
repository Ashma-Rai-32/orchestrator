# 0007. Multi-agent topology: tool-calling coordinator with skill pools

- Status: accepted
- Date: 2026-10-07

## Context and problem

A tenant's team is defined by database rows (employee name + skills) and changes at runtime. A platform coordinator must plan and delegate. Teams can contain many employees with identical skills (e.g. 10 React developers). We need a topology built from framework pieces that scales with headcount.

## Decision drivers

- Built at runtime from rows, no per-tenant code.
- Coordinator prompt/tool count must not grow linearly with identical employees.
- Parallel work, identifiable per employee in streams (for the office UI).
- Minimal custom code; framework stays behind the team-builder interface.

## Options considered

1. **`langgraph-supervisor` (`create_supervisor`)**: pre-1.0 (0.0.31). Its own README now recommends the tool-calling pattern instead "for most use cases". One handoff tool per agent.
2. **`langgraph-swarm`**: agents hand off to peers, no central planner. Conflicts with the product rule that a platform coordinator plans and assigns.
3. **Tool-calling coordinator, one tool per employee**: `create_agent` coordinator; each employee a tool. Simple, but tool schemas grow with headcount (1987 chars for 12 employees vs 923 pooled in the spike).
4. **Tool-calling coordinator, one tool per distinct skill set (pool)**: employees with identical skills share one delegation tool; the tool picks an available employee.
5. **`Send` fan-out from a planning node**: deterministic parallelism, but routing logic moves out of the model into graph code.

## Decision

Option 4. Every employee is a `create_agent(name=<employee>)` with a system prompt merged from its skills and `ModelCallLimitMiddleware` as a runaway guard. The coordinator is a `create_agent` whose tools are one delegation tool per skill set. Multiple tool calls in one coordinator turn run in parallel (seen in the spike). Option 5 remains available inside the graph where deterministic fan-out is needed.

## Consequences

- Good: 12 employees → 3 tools; adding the 11th React developer adds no prompt tokens.
- Good: only custom code is grouping rows and picking an employee from a pool (product logic).
- Bad: the coordinator cannot target a specific person in a pool; acceptable since they are interchangeable by definition. Revisit if employees gain individual memory/personality that matters for assignment.
- Follow-ups: replace round-robin with real availability (busy/idle from run state) in M1; verify parallel tool execution thread-safety of the picker.

## Sources

- Spike: `spikes/team-builder/` (langchain 1.4.3, langgraph 1.2.14), 2026-10-07
- langgraph-supervisor 0.0.31 README (PyPI), LangChain multi-agent guide: https://docs.langchain.com/oss/python/langchain/multi-agent
