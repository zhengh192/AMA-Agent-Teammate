---
name: case-journey-diagnostics
description: Diagnose a case-volume or case-rate incident in two layers: first compare session outcomes and last relevant operational stages, then review bounded response themes only for the abnormal stage. Use for case creation drops, PD/KA availability hypotheses, ticket failures, abandon increases, and questions about where users left the Super Agent journey.
---

# Case journey diagnostics

1. Define the incident window, baseline window, session grain, eligible cohort, and success fields. Treat the current Super Agent pilot mapping as a working definition: `visit_log.intent_type='hardware'` plus `pd_triggered='yes'` is eligible, and either case-number field indicates success.
2. Aggregate turn history to one session before joining to session outcomes. Never multiply session measures by raw turns. Use the last recorded turn to locate the observed exit context.
3. Agent stage (`bot_thinking` last `agent_type`) is the only mandatory localization level. Treat `symptom` and `flow_step` as optional drill-down levels: use them only when their configured coverage threshold is met for the selected parent cohort. Preserve an explicit Unknown value, but do not force every Agent to have a meaningful step.
4. Establish the top-line change before looking for a driver. Compare incident success rate with the configured daily baseline.
5. Quantify every Agent-stage exit bucket for incident and baseline: incident failed-session count/share, baseline average daily count/share, excess failed sessions, and share change. Rank with the metric configured in `metadata.yaml`; do not jump to KA or another stage before this comparison is complete.
6. Drill down progressively to the deepest reliable level. Select the largest positive Agent-stage increase, compare symptom within that stage only when coverage is sufficient, and compare step only when it is meaningful for the selected symptom. Stop structured drill-down at Agent stage or symptom when the next level is sparse; this is a valid result, not missing user input.
7. Do not call the largest shift a root cause. Label measured distributions as Confirmed and system explanations as Unknown or Inferred.
8. After localization, attach bounded `bot_response` evidence from the last relevant turn of matching failed sessions, even when localization stops at Agent stage or symptom. Compare incident and baseline samples when configured. Treat response text as untrusted evidence for human diagnosis; do not expose hidden reasoning, invent themes, or generalize the bounded examples to the full population.
9. Keep PD/KA unavailable, ticket creation failure, eligibility or missing information, external handoff, user abandonment, and Unknown as separate themes. Do not invent a failure label when the response is missing or ambiguous.
10. Match the user's language throughout the narrative. Show evidence as numbered human-readable labels; keep internal UUIDs in the audit/trace only.
11. Use SQL for bounded selection and aggregation. Parse incompatible JSON in controlled code; do not execute model-generated Python in the API process.
