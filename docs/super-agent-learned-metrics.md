# Super Agent learned metric layer

## Purpose

The local pilot can calculate before performing broader analysis. It resolves each Super Agent/UAT
question in this order:

1. an active user-taught metric definition in SQLite;
2. a Git-tracked active or explicitly labeled draft definition;
3. a direct physical session, turn, or telemetry count;
4. a targeted clarification asking for the table, aggregation, fields, filters, and rate conditions.

The planner does not call the model when a UAT definition can be resolved by these paths. This avoids
model latency for source and metric recognition.

## Teach-once workflow

When no unique definition exists, the Agent shows a preview of actual allowlisted fields. The user can
reply naturally or use the explicit form:

```text
指标名=Agent Handoff Rate; 表=visit_log; 统计方式=ratio;
统计字段=session_id; 时间字段=start_time;
分子条件=to_agent_flag:yes; 分母条件=全部;
别名=转人工率|handoff rate
```

The definition is activated only from that explicit conversation response. The service validates the
physical table and fields, rejects denied columns, versions prior definitions, emits an audit event,
and then creates a parameterized SQL plan. The user still approves the exact SQL before execution.

## Name tolerance

Resolution normalizes spacing, punctuation, case, Chinese/English mixed phrasing, and minor spelling
variation. Exact aliases win. A unique strong fuzzy match is accepted; multiple or closely scored
matches are returned for clarification. Missing definitions are never invented.

## Storage and visibility

- Authoritative project definitions remain Git-tracked under `knowledge/`.
- User-taught pilot definitions are stored in SQLite table `learned_metric_definitions`.
- Active learned definitions are visible under Admin → Knowledge and through
  `GET /api/learned-metrics`.
- Each analysis plan and trace includes `learned.metric_<id>` plus its semantic version.
- Raw clarification text is hashed in audit; safe table, aggregation, field, version, and alias-count
  metadata are retained.

## Current boundary

This path supports controlled `count`, `count distinct`, `sum`, `average`, `min`, `max`, and `ratio`
calculations over one allowlisted UAT table, optional scalar filters, a bounded date range, and an
optional approved dimension. It intentionally does not let model-generated assumptions overwrite
approved metadata, execute arbitrary SQL, or bypass the read-only SQL policy and approval interrupt.
Multi-table learned formulas and production governance remain future review items.