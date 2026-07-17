---
name: metric-query
description: Resolve approved metrics and prepare bounded read-only SQL for analytical questions.
---

# Metric query

1. Retrieve the active metric, dataset, field, relationship, and business-rule definitions.
2. Stop on missing, ambiguous, inactive, or schema-conflicting metadata.
3. Clarify period, grain, dimensions, and entity definition when material.
4. Generate one bounded read-only query proposal and pass it through AST and policy validation.
5. Wait for approval bound to the exact SQL, parameters, source, limits, and policy version.

Never invent a metric, table, field, relationship, or query result.
