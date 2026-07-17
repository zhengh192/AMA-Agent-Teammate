# Super Agent UAT Schema and Quality Gap

## Executive outcome

A user-authorized, one-time plaintext UAT connection succeeded on 2026-07-16. The endpoint is a
Doris engine exposing a MySQL-compatible protocol version of `5.7.99`, not standard MySQL. The
authenticated account has the `read_only` role, `Select_priv` on `sa_logs`, no global
privileges, and no observed write/DDL privileges.

The three expected tables exist. Catalog metadata and fixed aggregate checks were read; no raw
business rows or sensitive values were retrieved or persisted. Agent SQL routing is now available as an opt-in development pilot. Physical-count aggregates are authoritative; supported document-backed KPI formulas may run only as explicit working assumptions and remain non-production.

## Confirmed physical datasets

| Dataset | Physical table | Observed rows | Physical columns | Candidate ID | Current result |
|---|---|---:|---:|---|---|
| Session | `visit_log` | 7,071 | 78 | `session_id` | 7,071 non-null and 7,071 distinct |
| Turn | `turn_log` | 36,467 | 31 | `turn_id` | 36,467 non-null and 36,467 distinct |
| Frontend telemetry | `telemetry_log` | 8,462 | 7 | `event_id` | 8,462 non-null and 8,462 distinct |

All catalog columns are declared nullable by Doris, including the candidate IDs. This conflicts with
the draft semantic metadata that marks IDs non-nullable, even though the current snapshot contains no
missing or duplicate IDs. The physical contract and observed data quality must remain separate.

## Relationship quality

| Relationship | Child rows | Distinct child sessions | Unmatched rows | Unmatched sessions | Assessment |
|---|---:|---:|---:|---:|---|
| `turn_log.session_id ? visit_log.session_id` | 36,467 | 6,527 | 1 (0.0027%) | 1 (0.0153%) | Strong but not perfect |
| `telemetry_log.session_id ? visit_log.session_id` | 8,462 | 6,691 | 27 (0.3191%) | 8 (0.1196%) | Usable with an orphan warning |

Turn multiplicity averages 5.59 rows per represented session and reaches 126. Telemetry multiplicity
averages 1.26 events per represented session and reaches 40. Both are confirmed one-to-many
relationships; downstream joins must aggregate or otherwise control duplication.

## Date coverage

| Table | Earliest event time | Latest event time | Latest load/create time |
|---|---|---|---|
| `visit_log` | 2026-06-01 01:39:32 | 2026-07-16 01:36:25 | 2026-07-16 01:36:25 |
| `turn_log` | 2026-06-01 01:54:24 | 2026-07-15 10:18:34 | 2026-07-16 03:36:32 |
| `telemetry_log` | 2026-06-01 09:31:21 | 2026-07-16 12:06:10 | Not represented |

Timezone, ingestion SLA, and late-arrival behavior are unknown. These timestamps cannot yet support a
formal freshness SLA.

## High-impact completeness findings

| Field or concept | Missing | Risk |
|---|---:|---|
| `channel` | 5,894 / 7,071 (83.35%) | Channel breakdowns cover only a minority of sessions |
| `to_agent_flag` | 7,039 / 7,071 (99.55%) | Current WHTR/transfer-rate calculations would be unreliable |
| `touchless_exception` | 6,587 / 7,071 (93.16%) | Touchless and contribution analysis are not broadly supported |
| `agent_working_hour` | 5,383 / 7,071 (76.13%) | Working-hours denominators are incomplete |
| `intent_type` | 1,706 / 7,071 (24.13%) | Intent segmentation has material missingness |
| `survey_score` and `survey_resolved` | 7,012 / 7,071 (99.17%) | Only 59 sessions have survey responses; KPI coverage is 0.83% |

`is_foc` is physically complete but only 40 sessions are true (0.57%). Completeness does not prove
the FOC business rule is correct; its derivation remains undocumented.

## Domain conflicts with the 930 requirements

- `agent_working_hour` is a nullable string with values `True`/`False`, not a physical boolean.
- `to_agent_flag` is a nullable string populated as `yes` in only 32 rows, not a physical boolean.
- Survey scores observed are 0, 1, 5, 6, 7, 8, 9, and 10. The 930 workbook examples
  `1/3/5/9` are not a complete allowed-value definition.
- A threshold of score at least 8 is technically possible, but the accepted survey population and
  response-coverage rule still require approval.
- Doris reports no conventional indexes through `information_schema.STATISTICS`; Doris key-model
  and partition definitions still need a separate approved catalog method.

## 930 implementation gap

The database observation supports the user's statement that version 930 fields are not implemented.

Session fields modeled but absent from `visit_log`:

- `auto_driver_download`
- `eligible_feature`
- `failure_reason`
- `is_cru_eligible`
- `logged_in`
- `msd_wo_deliver_type`
- `sa_creation_deliver_type`
- `use_camera_tracking`
- `use_rt_voice`

Turn fields modeled but absent from `turn_log`:

- `auto_driver_download_confirm`
- `camera_event`
- `camera_exit_reason`
- `camera_failure_reason`
- `camera_on`
- `driver_download_fail_reason`
- `driver_download_result`
- `driver_update_required`
- `driver_version`
- `feature_enable`
- `voice_exit_reason`
- `voice_failure_reason`
- `voice_on`

The current semantic registry also under-models deployed data: 62 `visit_log` columns, 28
`turn_log` columns, and 3 `telemetry_log` columns are present but not represented. Their physical
existence is confirmed, but their business meaning must be reviewed before definitions are created.

## Sensitive-column boundary

At minimum, deny row-level access to transcript/payload and direct identifier fields such as
`chat_log`, `chat_log_text`, `chat_summary`, `user_input`, `bot_thinking`,
`bot_response`, `user_info`, `customer_information`, `msd_customer_info`,
`msd_shipping_info`, `serial_number`, `msd_wo_sn`, and `event_data`. This list is
conservative and still requires enterprise data-classification review.

## Decisions needed before metric activation

1. Confirm timezone and which event/load date controls reporting.
2. Define missing-value behavior for transfer, working-hours, touchless, FOC, intent, and channel.
3. Approve the survey population, score scale, and minimum coverage reporting.
4. Confirm whether `visit_log.session_id` is the durable parent key despite nullable DDL.
5. Decide whether the small orphan rates are expected late arrivals or data-quality defects.
6. Provide the Doris key/partition model and pipeline owner.
7. Enable TLS or an approved encrypted tunnel before production Agent connectivity.

Until these decisions are approved, the database facts are authoritative for physical availability,
while KPI formulas and semantic interpretations remain draft.
