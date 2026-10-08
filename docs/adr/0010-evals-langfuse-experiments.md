# 0010. Evaluation harness on Langfuse experiments

- Status: accepted (chosen by the maintainer)
- Date: 2026-10-08

## Context and problem

M7 compares agent-system variants (models, team set-ups, prompts) on the same briefs, with reproducible scores. Real runs already showed behaviours worth measuring: a coordinator that assigned testing before building, a tester stuck without a preview server, and a summary claiming "built and verified" when no verification happened. We need a harness that runs benchmark goals against configurations and scores the outcomes, without hand-writing an experiment runner.

## Decision drivers

- Reuse the observability stack: scores next to the traces they came from.
- Variants are configuration, not code.
- Cheap, mostly deterministic evaluators; LLM-as-judge only where needed.
- Runnable on the fake model (CI, development) and on real models (research runs).

## Options considered (checked 2026-10-08)

1. **Langfuse experiments** (SDK 4.17.0, already in the stack): `Langfuse.run_experiment(data, task, evaluators, run_evaluators)` runs items concurrently, traces each, attaches scores, and compares runs in the Langfuse UI.
2. **Inspect AI 0.3.277** (UK AI Security Institute, MIT): research-grade agent evals with tasks, solvers, scorers and a log viewer; its own sandboxing model; results live outside Langfuse.
3. **DeepEval 4.2.8**: metric library oriented to LLM/RAG outputs; less suited to multi-agent runs that produce websites.
4. Hand-written runner: rejected by the project rule.

## Decision

Option 1. The harness (`experiments/` workspace package) drives the agent system **in-process**: the same team builder, sandbox, toolsets and checkpointer as the worker, with the model, team and prompts taken from a named configuration. Product plumbing (HTTP API, database, Keycloak, queue) is out of the loop, so experiments are fast, isolated and reproducible.

- Benchmarks: `experiments/benchmarks.toml` (brief + expected page keywords).
- Configurations: `experiments/configs.toml` (model, fallbacks, team).
- Evaluators: finished, has `index.html`, brief coverage, steps, duration (7a); site loads in Chromium, cost, honesty (7b).

## Consequences

- Good: one UI for traces and scores; variants compared side by side.
- Good: no product changes needed to run research.
- Bad: harness bypasses the API, so product-level failures (queue, auth) are not measured here; those stay covered by the API tests.
- Bad: free-tier quotas (20 requests/day/model on Gemini) limit real-model runs; use the fallback chain or local models for larger sweeps.
- Follow-up: an Inspect AI adapter if a more formal research write-up needs it.

## Sources

- Installed langfuse 4.17.0: `Langfuse.run_experiment`, `langfuse.experiment` (item, task, evaluator types).
- PyPI: inspect-ai 0.3.277, deepeval 4.2.8 (2026-10-08).
