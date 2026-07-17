# Analysis Output Contract

All P0 Skills produce or contribute to the shared `AnalysisResult` model. The existing Phase 2
dataset, computation, chart, artifact, and join-quality fields remain compatible. The foundation
contract adds:

| Field | Contract |
|---|---|
| `executive_summary` | Concise outcome with analysis type and data confidence. |
| `confirmed_findings` | Evidence-linked observations directly supported by validated data. |
| `inferred_findings` | Evidence-linked interpretations explicitly labeled `Inferred`. |
| `unknowns` | Questions the available evidence cannot answer. |
| `recommendations` | Next actions bounded by evidence and confidence. |
| `limitations` | Data, method, join, sample, and causal limitations. |
| `evidence` | Reproducible calculation and query/dataset links. |
| `charts` | Zero or more validated useful Plotly specifications. |
| `metric_references` | Authoritative metric definition IDs and versions. |
| `data_source_references` | Logical source IDs used by approved queries. |
| `executed_query_references` | Audited query proposal/execution IDs. |
| `skill_references` | Selected foundation Skill IDs and versions. |
| `data_confidence` | `high`, `medium`, `low`, or `unusable`. |

Material conclusions require evidence IDs. `Confirmed` means directly supported; `Inferred` means
an interpretation; `Hypothesis` needs testing; `Unknown` means insufficient evidence; `Need
confirmation` requires a user or owner decision. Contribution and correlation never establish
causation. A low or unusable dataset cannot support a high-confidence conclusion.

Chart recommendations cover line, bar, stacked bar, 100% stacked bar, scatter, histogram,
waterfall, funnel, and table. A chart is omitted or falls back to a table when it does not improve
understanding or fails validation.
