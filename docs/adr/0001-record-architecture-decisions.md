# 0001. Record architecture decisions

- Status: accepted
- Date: 2026-10-07

## Context and problem

Staffroom combines several fast-moving frameworks (LangGraph, LangChain, Langfuse, Phaser 4). Choices will be revisited as those frameworks change, and the project doubles as a portfolio where the reasoning matters as much as the code. We need a lightweight, durable way to record why things are the way they are.

## Decision drivers

- Reasoning must survive context loss (new sessions, new contributors, AI agents).
- Low ceremony: writing one should take minutes.
- Lives in the repo, reviewed like code.

## Options considered

1. **MADR-style Markdown files in `docs/adr/`**: plain Markdown, numbered, one decision per file.
2. **Nygard's original ADR format**: Context / Decision / Consequences only; no explicit alternatives section.
3. **Wiki or external doc tool**: easy to edit, but drifts from code and is invisible in PRs.
4. **No formal records, commit messages only**: zero overhead, but reasoning is scattered and alternatives are lost.

## Decision

Option 1, a trimmed MADR template ([0000-template.md](0000-template.md)). MADR's explicit "Options considered" section matches the project rule that every significant choice lists alternatives. Files are numbered sequentially and never renumbered; a superseded ADR stays and links to its replacement.

## Consequences

- Good: decisions are reviewable in PRs and greppable by agents.
- Good: `docs/plans/STATUS.md` can link to ADRs instead of repeating reasoning.
- Bad: small overhead per decision; mitigated by keeping the template short.

## Sources

- MADR: https://adr.github.io/madr/
- Michael Nygard, "Documenting Architecture Decisions" (2011)
