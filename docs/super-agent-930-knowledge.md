# Super Agent 930 Data Requirements Knowledge Note

## Authority and lifecycle

- Project name: **Super Agent**.
- Primary source: `930_Super_Agent_Data_Requirements_20260713.xlsx`, dated 2026-07-13.
- User-confirmed lifecycle: every field marked `Version = 930` is a future requirement and is **not implemented**.
- Version 930 content may be used to explain intended requirements, gaps, and design questions. It
  must not be presented as an available database field, queried by SQL, or used as confirmed
  evidence of current product behavior.
- The workbook is a requirements source, not proof of a deployed physical schema. Database type,
  table names, refresh design, and several definitions remain open.

## Product and analytical scope

Super Agent combines multiple AI and service capabilities into one service experience. The workbook
organizes measurement around five Level 1 dimensions:

1. Cost Savings — WHTR, Touchless Rate, Partial Touchless Rate, FOC, and observed downstream FS KPIs.
2. Revenue — Super Agent-attributed GMV.
3. Customer Experience — T3B and FCR.
4. AI Penetration — SA Contact Rate and SA Ticket Rate.
5. Journey Efficiency — Time to Resolution and Contacts per Resolution.

The recommended cadence is weekly operational review and monthly business review. Proposed analysis
units are session, contact, ticket, and resolution path. Downstream FS KPIs may be influenced by
Super Agent but are not automatically owned or caused by it.

## Dataset model

- `super_agent.session`: one proposed row per service session. It contains core geography, channel,
  intent, product, service-flow, survey, transfer, case, and outcome attributes.
- `super_agent.turn`: one proposed row per user-agent interaction turn. It contains user input,
  agent output, flow/step, content source, strategy, tool/reasoning metadata, and feature events.
- `super_agent.frontend_event`: one proposed row per frontend request or event.
- `super_agent.case`: one proposed row per eTicket case with downstream MSD/work-order attributes.
- Session-to-turn and session-to-frontend-event are proposed one-to-many relationships through
  `session_id`. Session-to-case is also one-to-many, but automatic joining is not approved because
  one session can create multiple cases and can mention multiple serial numbers.

## KPI requirement interpretations

### WHTR

Proposed formula: distinct eligible sessions transferred to a human agent during working hours,
divided by all distinct eligible Super Agent sessions during working hours. Transfer is proposed to
start when the MSD link request is initiated. The working-hours calendar and eligibility rules are
not defined, so this metric remains draft.

### Touchless and Partial Touchless Rates

Proposed grain is case/ticket, not session. Numerators are distinct eligible cases classified as
`touchless` or `partial touchless`; the denominator is all eligible cases created by Super Agent.
The multi-case session model and final classification rules remain unresolved.

### FOC

Proposed formula: distinct eligible sessions resolved within the same Super Agent session divided by
all eligible sessions. Proposed prerequisites include no case creation and no human transfer.
Resolution evidence may include user feedback, survey score, and an LLM judgment, but the accepted
logic and chat-versus-eTicket treatment are not approved.

### Survey metrics

- T3B: submitted surveys with score at least 8 divided by all submitted surveys.
- FCR: submitted resolution surveys answered `yes` divided by all submitted resolution surveys.

Both require response-coverage reporting. FCR also requires an approved repeat-contact window. The
session sheet lists example survey values `1/3/5/9`, which does not fully define a scale for a
threshold of 8; this must be confirmed.

### Downstream and incomplete metrics

- RRR, NPRA, and PPSN refer to existing FS logic that is not reproduced in the workbook. They should
  be treated as Unknown until the approved formulas and MSD fields are supplied.
- GMV requires an approved Super Agent attribution field/filter in eService APOS data.
- SA Contact Rate and SA Ticket Rate have no numerator or denominator logic in the workbook.
- Time to Resolution does not choose median versus average or define the effective endpoint.
- Contacts per Resolution does not define contact identity, resolution identity, or journey window.

## Version 930 session requirements — not implemented

- `msd_wo_deliver_type`
- `logged_in`
- `eligible_feature`
- `use_rt_voice`
- `use_camera_tracking`
- `auto_driver_download`
- `failure_reason`
- `is_cru_eligible`
- `sa_creation_deliver_type`

## Version 930 turn requirements — not implemented

- `input_type` additions for voice and camera
- `feature_enable`
- `voice_on`, `voice_failure_reason`, `voice_exit_reason`
- `camera_on`, `camera_event`, `camera_failure_reason`, `camera_exit_reason`
- `driver_update_required`, `auto_driver_download_confirm`, `driver_download_result`
- `driver_version`, `driver_download_fail_reason`

## Version 930 frontend requirements — not implemented

The frontend event taxonomy must add real-time voice enablement, camera tracking enablement, and
automatic driver-download events. `event_data` should carry feature API success/error details, but
the JSON schema and redaction rules are not defined.

## Open P1 decisions

- Preserve historical KPI continuity while moving to Super Agent definitions.
- Choose the physical database and Power BI integration model; business expects at least hourly refresh.
- Define how one session with multiple cases or serial numbers is represented.
- Define the impact of switching between solution modes within one session and whether KPIs split by mode.
- Decide whether an LLM fallback concept still exists.
- Approve encryption, masking, access, and retention for user, transcript, shipping, serial-number,
  and feature-event payloads.

## Agent behavior

- Treat the workbook and this note as source-backed Knowledge.
- Treat structured `super_agent.*` definitions in the semantic registry as `draft` requirements.
- Never use draft definitions for SQL planning.
- Label exact workbook statements as Confirmed requirements, interpretations as Inferred, missing
  formulas or schema as Unknown, and open design choices as Need confirmation.
- Do not silently inherit an older product's metric formula merely because the workbook says to keep
  existing logic; require the referenced approved definition.
