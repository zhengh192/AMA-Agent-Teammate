# Analysis Skill Authoring Guide

## Create or compose

Create a new Skill only when the method has a distinct trigger, input/output contract, risk or
approval profile, or reusable deterministic calculation. Reuse an existing Skill when only the
metric, dataset, dimension, or presentation changes. Compose prerequisites when one reviewed
procedure must succeed before another can run; do not create another Agent.

## Package contract

Each foundation Skill uses `skills/<skill_id>/metadata.yaml`, `SKILL.md`, and asserted cases under
`tests/`. IDs use lowercase snake case and versions use semantic `MAJOR.MINOR.PATCH` values.

Put in `metadata.yaml`:

- identity, status, version, owner, reviewer, dates, aliases, and English/Chinese triggers;
- supported analysis intents and required semantic metadata;
- typed inputs and outputs;
- prerequisite Skills, required tools, deterministic operations, risk, and approval settings.

Put in `SKILL.md`:

- the concise methodology and decision order;
- clarification and stop conditions;
- interpretation, evidence, causality, and response requirements.

Put in deterministic code:

- arithmetic, reconciliation, null/duplicate/freshness checks, match rates, threshold checks,
  policy validation, and evidence linkage that must be reproducible;
- never model-generated Python or unrestricted execution in the API process.

## Tests

Add positive calculation/selection cases and negative safety/ambiguity cases. Assert behavior and
numeric results, not only serialized snapshots. Run:

```powershell
uv run python scripts/validate_analysis_skills.py validate
uv run python scripts/evaluate_analysis_skills.py
uv run pytest
```

## Version and deprecation

- Patch: clarification or test change without contract meaning change.
- Minor: backward-compatible trigger, output, or deterministic-operation extension.
- Major: incompatible input, output, calculation, policy, or interpretation change.

Keep historical versions in Git. Set the old package to `deprecated` before activating an
incompatible replacement. Only one effective active version of an ID is allowed. Do not activate a
model-generated change; natural-language activation remains postponed.
