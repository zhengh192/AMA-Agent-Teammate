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
validates SQL. The plan, approval payload, safe plan API, and audit trace include the selected
metric definition ID/version and applicable relationship references.

If an alias maps to multiple active metrics, the LangGraph run interrupts and asks for an exact
metric ID. If no active definition matches, the run stops with `Unknown`; it does not invent a
definition. A model-generated assumption remains untrusted context and never changes approved YAML.

## Change workflow

1. Edit or add YAML with a new semantic version; do not silently mutate the meaning of an existing version.
2. Keep the previous definition and mark it `deprecated` when history must remain queryable.
3. Run the CLI and backend tests.
4. Review ownership, source, effective dates, sensitivity, join risks, and business-rule references.
5. Commit the YAML, tests, and any documentation together.

The AIR examples are semantic contracts only. Their connectors are intentionally not configured in
the local demo, so an AIR analysis stops with a connector conflict until read-only AIR connections
and physical schema catalogs are explicitly approved and configured.
