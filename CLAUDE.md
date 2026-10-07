# CLAUDE.md

Guidance for AI coding agents working in this repo. Humans: see [README.md](README.md).

## Start here every session

1. Read [docs/plans/STATUS.md](docs/plans/STATUS.md): current step, open questions, decision log.
2. Read the current milestone in [docs/plans/roadmap.md](docs/plans/roadmap.md).
3. Check [docs/adr/](docs/adr/) before proposing anything already decided.
4. Work in **small increments**: one concept per step, run it and show the output, explain what the framework did, then stop for review. The maintainer is learning the frameworks and wants control.
5. After finishing a step, update `STATUS.md` and propose a Conventional Commit message.

## The rule

Adopt well-maintained frameworks and libraries for anything commodity. Write code only for what is unique to Staffroom. **If you are about to hand-write something a framework already provides, stop and say so.**

Before using any library API: check the current version (PyPI/npm) and read current docs. Flag anything deprecated.

## Hard constraints

- **Never commit or push.** The maintainer commits. Propose small Conventional Commit messages instead (`feat:`, `fix:`, `docs:`, `build:`, `ci:`, `chore:`, `test:`, `refactor:`).
- ADR in `docs/adr/` (MADR format, see `0000-template.md`) for every significant choice, with alternatives considered.
- Provider-specific model code lives in **one** adapter module. Use LangChain `init_chat_model`; providers switch by config.
- Frameworks stay behind small interfaces (Protocols) so they can be swapped.
- Synthetic data only. No code, data or terminology from any employer.
- Secrets never appear in prompts, logs, traces or events. Agents reference secrets by name; tools resolve them.
- Generated code runs only in the sandbox.
- Nothing goes public without explicit admin approval (LangGraph interrupt).
- Tenant isolation is enforced by Postgres row-level security; tests must prove it.

## Layout

```
apps/api/          FastAPI backend + agent core (Python)
apps/office/       Phaser 4 office UI (TypeScript, Vite, no React)
packages/schemas/  Shared Pydantic models
sandbox/           Execution sandbox for generated code
infra/             Compose includes, Terraform (later)
experiments/       Research harness (M7)
spikes/            M-1 framework spikes (PEP 723 scripts, never imported by apps)
docs/adr/          Architecture decision records
docs/frameworks/   Per-framework findings
docs/plans/        Roadmap and status (working memory)
```

## Commands

```bash
uv sync                                   # install workspace + dev tools
uv run pre-commit run --all-files         # ruff, format, gitleaks, hygiene
uv run pytest                             # tests
docker compose up -d                      # Postgres + Redis
docker compose --profile observability up -d   # + Langfuse at http://localhost:3000
uv run spikes/<name>/main.py              # run a spike
```

## Conventions

- Python 3.12+, typed (`mypy --strict` on `apps/` and `packages/`), ruff for lint and format.
- Async SQLAlchemy 2, Pydantic v2, pydantic-settings for config.
- Tests use a deterministic fake chat model; real-model runs are opt-in via env flag.
- Keep `README.md` status table honest: real vs stubbed.
