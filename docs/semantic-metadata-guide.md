# Semantic Metadata Registry Guide

The semantic metadata registry is the approved, Git-versioned contract used by the analysis
planner before it creates SQL. It is intentionally separate from uploaded Knowledge, Skills,
Memory, model prompts, and database checkpoints. Model output and agent assumptions cannot modify
or override this registry.

## Layout and ownership

```text
knowledge/
  data_sources/       # One strict data-source file with nested datasets per YAML file
  fields/             # Strict field collections
  metrics/            # Strict metric collections
  relationships.yaml  # Independently versioned relationship definitions
  business_rules.yaml # Independently versioned, referenceable business rules
```

Every definition carries `id`, semantic `version`, lifecycle `status`, `owner`, provenance
`source`, `effective_from`, optional `effective_to`, and `last_reviewed_at`. Git history records
the file-level review history; the definition version records the business contract version.
Only active definitions inside their effective-date range are authoritative for planning.

The schemas reject unknown keys and constrain IDs, semantic versions, enums, dates, list sizes,
and relationship references. A data source is always read-only. Fields explicitly describe grain,
semantic type, nullability, allowed values, join usage, sensitivity, and caveats. Metrics explicitly
describe components, formulas, distinct logic, filters, exclusions, time logic, dimensions, source
datasets, cautions, and referenced business rules.

## Validation and deployment behavior

Validate a proposed change before review:

```powershell
uv run python scripts/validate_semantic_metadata.py validate
```

The API validates every YAML file at startup. In `development` and `test`, any invalid active
definition fails startup. In `production`, invalid definitions are excluded and each rejection
emits a sanitized `semantic_metadata.definition.rejected` audit event. Production audits include
only the path, validation code, definition ID/version when available, and active flag; raw YAML and
secrets are not logged.

Schema consistency is checked again when a metric is selected. A referenced dataset, physical
table, field, or field nullability that conflicts with the configured connector catalog stops the
plan before SQL generation. A metadata-only source without a configured connector is discoverable
through the API but cannot be queried.

## Read-only API

- `GET /api/semantic-metadata` lists definitions; filter with `definition_type` and `status`.
- `GET /api/semantic-metadata/search?q=conversion` searches IDs, names, descriptions, and metric aliases.
- `GET /api/semantic-metadata/{definition_type}/{id}?version=1.0.0` retrieves one definition.

Definition types are `data_source`, `dataset`, `field`, `metric`, `relationship`, and
`business_rule`. These endpoints do not update metadata. Natural-language metadata updates are
deliberately postponed.

## Analysis behavior

The planner first obtains a structured analytical intent, then resolves the active metric and its
fields and relationships, checks them against the connector catalog, and only then creates and
validates SQL. The plan, approval payload, safe plan API, audit trace, and result artifact include the selected
metric definition ID/version, applicable relationship references, and active dataset business-rule
IDs/versions. Business-rule expressions are parsed and then passed through the same SQL AST policy
gateway as the rest of the query.

If an alias maps to multiple active metrics, the LangGraph run interrupts and asks for an exact
metric ID. If no active definition matches, the run stops with `Unknown`; it does not invent a
definition. A model-generated assumption remains untrusted context and never changes approved YAML.

## Change workflow

1. Edit or add YAML with a new semantic version; do not silently mutate the meaning of an existing version.
2. Keep the previous definition and mark it `deprecated` when history must remain queryable.
3. Run the CLI and backend tests.
4. Review ownership, source, effective dates, sensitivity, join risks, and business-rule references.
5. Commit the YAML, tests, and any documentation together.

The Super Agent 930 workbook is stored as source-backed Knowledge and represented as draft semantic
metadata. Draft definitions are visible in the registry API but never participate in SQL planning.
Version 930 fields are explicitly marked not implemented; activation requires owner approval,
read-only connector configuration, and validation against the physical schema.


## Current Super Agent population rule

'Super Agent Valid User Traffic Population' is active as
'super_agent.valid_user_traffic_population@1.0.0'. It applies to visit, turn, and telemetry
datasets. Direct visit calculations use its approved condition; turn and telemetry calculations
inherit the population through session membership in visit_log. The Knowledge admin page exposes
the active version, expression, owner, provenance, applicable datasets, and caveats. A meaning
change requires a reviewed new semantic version.
## Cohort-to-detail semantics

Some questions select a population at one grain and request output at another. Keep these concepts
separate:

- the cohort dataset owns population filters and the requested date window;
- the output dataset owns the returned fields, output-only filters, and row grain;
- one active relationship with `automatic_join_allowed: true` supplies the entity-key mapping;
- the relationship ID/version is included in the analysis trace;
- missing, ambiguous, inactive, or schema-conflicting relationships stop planning.

For example, "sessions where `visit_log.is_device_switch=true`, return all `turn_log` content"
uses `super_agent_uat.visit_to_turn@1.0.0`. The generated SQL enumerates all permitted turn fields,
selects session IDs in a bounded visit subquery, preserves one row per turn, and orders by session
and turn time. It does not count turns and does not apply the session flag to `turn_log`.
