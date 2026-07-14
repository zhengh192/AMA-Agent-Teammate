# Observability and Audit

## Goals

Provide enough telemetry to operate, debug, reproduce, secure, and review the system without recording private chain-of-thought or leaking sensitive data.

## Correlation model

Every operation propagates `session_id`, `run_id`, optional `job_id`, graph `thread_id`, trace/span IDs, and request IDs from approved providers/sources. IDs are opaque and safe to share in user-facing error summaries where policy allows.

## Required audit fields

- event ID and timestamp
- authenticated actor/service identity
- session, run, job, graph node, logical agent role
- model deployment profile and provider request ID
- prompt/template and policy versions
- tool/connector name and input hash
- data-source and source-policy versions
- normalized SQL or protected SQL reference, parameter hash/redaction
- start/end/duration, status, retry/attempt
- token usage, row count, result bytes
- approval event and exact payload hash
- artifact/evidence references and classification
- sanitized error category/code

## Event families

`identity.*`, `session.*`, `run.*`, `graph.node.*`, `model.*`, `tool.*`, `query.*`, `artifact.*`, `approval.*`, `knowledge.*`, `skill.*`, `memory.*`, `job.*`, `notification.*`, `policy.*`, and `security.*`.

## Traces, metrics, and logs

- **Traces**: API request -> graph nodes -> provider/tool/source calls -> artifact/evidence creation. Sampling must retain errors and security/approval events.
- **Metrics**: run success/latency, clarification/approval wait, node/provider/query latency, token use, rate limits/retries, SQL denials, rows/bytes, queue depth, job outcomes, retrieval quality, chart validation, and redaction failures.
- **Logs**: structured operational events with safe codes and correlation IDs. Raw prompts, responses, documents, rows, tokens, secrets, and auth claims are off by default.

## Audit versus telemetry

Audit is durable evidence of security/business decisions and uses append-oriented restricted storage and explicit retention. Telemetry is operational and may be sampled/aggregated. An audit event may reference a trace, but loss or sampling of telemetry cannot remove approval/query/governance history.

## Redaction and access

- Redact before serialization/export, not only in the viewer.
- Maintain central key/field detectors plus source-specific denied-field metadata.
- Store hashes/counts/references when raw values are unnecessary.
- Apply role-based access to logs, audit, traces, and artifacts; administrator access is itself audited.
- Test redaction with canary secrets and representative PII.

## Evidence view

User-visible trace shows the auditable plan, actions, queries, calculations, evidence, decisions, timing, and limitations. It never exposes hidden reasoning. Each conclusion opens its evidence record and protected supporting artifact according to authorization.

## Alerts

Alert on repeated auth/policy denial, approval replay, unexpected write attempt, denied-column access, data-volume anomaly, provider/source error surge, redaction failure, runaway token/query usage, stuck jobs, audit export failure, and integrity/retention failure.

## SLOs to define before production

- API/stream availability and latency
- Run completion/error rates by task type
- Approval and job queue delay
- Maximum audit event loss/export delay
- Checkpoint restore success and recovery time
- Data freshness/quality thresholds
- Security-event response time

No numerical production SLO is assumed in Phase 0.

## Testing and operations

- Contract tests assert required event fields and correlation propagation.
- Security tests assert secrets/sensitive fields never reach logs.
- Failure-injection tests cover provider/source timeout, checkpoint resume, duplicate approval, cancellation, and audit sink failure.
- Backup/restore and retention deletion are exercised before pilot.
- Runbooks cover provider outage, database outage, stuck checkpoint/job, data exposure, credential compromise, and rollback.
