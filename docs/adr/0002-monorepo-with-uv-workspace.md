# 0002. Monorepo with a uv workspace

- Status: accepted
- Date: 2026-10-07

## Context and problem

Staffroom has a Python backend (`apps/api`), shared Python models (`packages/schemas`), a TypeScript frontend (`apps/office`), infrastructure code, and throwaway framework spikes. We need to decide how to structure and manage dependencies for these.

## Decision drivers

- One clone, one CI pipeline, atomic changes across API and schemas.
- Fast, reproducible Python installs with a single lockfile.
- Spikes must not pollute the application lockfile.
- Avoid adding a JS monorepo tool for a single frontend package.

## Options considered

1. **Monorepo, uv workspace for Python, plain npm for the office app**: one `uv.lock` for `apps/api` + `packages/schemas`; `apps/office` has its own `package.json`.
2. **Monorepo with Poetry or PDM**: mature, but slower and with weaker workspace support than uv.
3. **Monorepo with Nx, Pants or Bazel**: polyglot task graphs and caching; heavy for one Python app and one frontend.
4. **Polyrepo** (api, office, infra separate): clean boundaries, but cross-repo changes and schema sharing become painful for a solo project.

## Decision

Option 1. The repo root is a **virtual uv workspace** (no `[project]` of its own) that holds shared dev tooling (ruff, mypy, pytest, pre-commit) in a `dev` dependency group. `apps/api` and `packages/schemas` join as workspace members when they are created in M0. Spikes are standalone PEP 723 scripts run with `uv run`, so their dependencies never enter `uv.lock`. The office app uses npm; TypeScript types are generated from the API's OpenAPI schema rather than shared source.

## Consequences

- Good: a single `uv sync` sets up all Python code; CI caches one lockfile.
- Good: spikes can pin any framework version without conflicts.
- Bad: two package managers (uv and npm). Acceptable for two languages.
- Follow-ups: revisit Nx/Pants only if build times or package count grow substantially.

## Sources

- uv workspaces: https://docs.astral.sh/uv/concepts/projects/workspaces/ (uv 0.12.x, checked 2026-10-07)
- PEP 723 inline script metadata: https://peps.python.org/pep-0723/
