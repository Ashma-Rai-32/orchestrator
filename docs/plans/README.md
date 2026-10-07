# Plans

Working memory for this repo. Anyone (human or agent) picking up work starts here.

| File | Purpose | Update when |
|---|---|---|
| [STATUS.md](STATUS.md) | Where we are, what's next, open questions, decision log | After every finished step / commit |
| [roadmap.md](roadmap.md) | Milestones M-1..M7 with file-level tasks: framework that does the work vs. custom code that remains | When scope or approach changes |

## Session start checklist

1. Read `STATUS.md` → "Next step" and "Open questions".
2. Read the section of `roadmap.md` for the current milestone.
3. Check `docs/adr/` for decisions already made — don't re-litigate them.

## Rules (from the project brief)

- Adopt well-maintained frameworks for anything commodity; write code only for what is unique to Staffroom. If about to hand-write something a framework provides, stop and flag it.
- Verify current package versions and read current docs before using an API; flag deprecations.
- Small Conventional Commits, one per finished step. ADR for every significant choice.
- Provider-specific model code lives in one adapter module. Frameworks stay behind small interfaces.
- No Clevero code, data or terminology. Synthetic data only.
- Secrets never in prompts, logs or events. Generated code runs only in the sandbox. Nothing goes public without admin approval.
