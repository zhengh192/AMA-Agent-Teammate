---
name: cross-source-reconciliation
description: Reconcile bounded approved source results and report match, duplication, and join quality.
---

# Cross-source reconciliation

Execute each approved source query independently. Validate join keys, cardinality, type coercion, and duplication risk before the bounded DuckDB join. Calculate match and unmatched rates deterministically. Warn when join quality is weak and never silently multiply rows.
