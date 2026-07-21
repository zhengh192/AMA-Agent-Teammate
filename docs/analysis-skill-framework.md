# Foundation Analysis Skill Framework

## Purpose

The Foundation Data Analysis Skill Pack is a Git-versioned procedural layer used by the existing
Data Analyst workflow. A Skill is not an Agent and is not merely a prompt. It combines strict
machine-readable metadata, concise methodology, named deterministic operations, and asserted test
cases. LangGraph remains the only orchestration runtime.

## Boundaries

- `knowledge/` is the authoritative semantic contract for approved metrics, datasets, fields,
  relationships, and business rules.
- `skills/<skill_id>/` contains the reviewed foundation skills loaded at application startup.
- `skills/registry/` remains the separate destination for user-proposed Skills that passed the
  existing exact-hash approval lifecycle.
- `policies/` contains human-readable, Git-versioned analysis, evidence, and SQL policies.
- `evals/` contains deterministic regression cases. It is not a production data store.

Unapproved or model-generated Skill content never enters the foundation registry. The registry
loads only immediate child directories that contain both `metadata.yaml` and `SKILL.md`.

## Runtime order

1. Retrieve bounded active metric and dataset candidates from semantic metadata.
2. Identify a structured analysis intent through the provider interface.
3. Resolve the exact authoritative metric, fields, datasets, and relationships.
4. Retrieve relevant active Skills and recursively resolve active prerequisites.
5. Construct and persist an explicit ordered Skill execution plan.
6. Generate and validate SQL, then use the existing exact-payload approval interrupt.
7. Execute read-only queries and deterministic calculations.
8. Validate evidence and assemble the shared `AnalysisResult`.

The model does not receive every Skill body. Selection uses metadata, aliases, localized trigger
examples, analysis intents, and prerequisites. Runtime plans retain only Skill IDs, versions,
required metadata, deterministic operation names, and approval requirements.

## Startup and production behavior

Every active Skill is validated with strict Pydantic models. Development and test startup fail on
an invalid active Skill, duplicate active ID, or inactive/missing prerequisite. Production rejects
the invalid package and emits a sanitized `analysis_skill.definition.rejected` audit event. Raw
Skill content is not written to that event.

## Failure behavior

A failed prerequisite stops its dependent Skill. Missing or ambiguous metric, period, grain,
baseline, or entity definition returns clarification. Low or unusable data confidence caps the
strength of conclusions. Contributions, decompositions, correlations, and calendar patterns are
not causal proof.
