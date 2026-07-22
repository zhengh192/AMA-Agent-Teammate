import type { AnalysisResult } from "./analysisTypes";
import { PlotlyFigure } from "./PlotlyFigure";

interface AnalysisResultTimelineProps {
  result: AnalysisResult;
}
interface DiagnosticRow {
  value: string;
  baseline_average_daily_count: number;
  incident_average_daily_count: number;
  excess_failed_sessions: number;
  failure_share_change: number;
}

interface DiagnosticLevel {
  key: string;
  label: string;
  parent: Record<string, string>;
  display_rows: DiagnosticRow[];
}

interface ResponseSample {
  comparison_date: string | null;
  agent_stage: unknown;
  symptom: unknown;
  flow_step: unknown;
  bot_response: string;
}

interface ResponseEvidenceSummary {
  selected_path: Record<string, string>;
  incident_sample_count: number;
  baseline_sample_count: number;
  samples: {
    incident: ResponseSample[];
    baseline: ResponseSample[];
  };
}

function formatNumber(value: number) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value);
}

export function AnalysisResultTimeline({ result }: AnalysisResultTimelineProps) {
  const finalDataset = result.datasets.at(-1) ?? null;
  const chinese = result.computation.summary.response_language === "zh-CN";
  const evidenceLabels = new Map(
    result.computation.evidence.map((item, index) => [item.id, index + 1]),
  );
  const diagnosticHierarchy = Array.isArray(result.computation.summary.hierarchy)
    ? result.computation.summary.hierarchy as DiagnosticLevel[]
    : [];
  const responseEvidence = (
    result.computation.summary.response_evidence
    && typeof result.computation.summary.response_evidence === "object"
  )
    ? result.computation.summary.response_evidence as ResponseEvidenceSummary
    : null;
  const displayColumns = finalDataset?.columns.filter(
    (column) => column !== "record_type" && !column.startsWith("bot_response_"),
  ) ?? [];
  const displayRows = finalDataset?.rows.filter(
    (row) => row.record_type !== "response_evidence",
  ) ?? [];
  const epistemicLabel = (value: string) => {
    if (!chinese) return value;
    return { Confirmed: "已确认", Inferred: "推断", Unknown: "尚不确定" }[value] ?? value;
  };
  const evidenceReference = (ids: string[]) => ids
    .map((id) => evidenceLabels.get(id))
    .filter((value): value is number => value !== undefined)
    .map((value) => (chinese ? `依据${value}` : `Evidence ${value}`))
    .join(chinese ? "、" : ", ");
  if (!finalDataset) return null;

  return (
    <section
      className="analysis-results timeline-result"
      aria-label={chinese ? "分析结果" : "Analysis results"}
      data-run-id={result.run_id}
    >
      <div className="result-toolbar">
        <div>
          <span className="eyebrow">{chinese ? "已完成" : "Completed"}</span>
          <h2>{chinese ? "分析结果" : "Bounded analysis result"}</h2>
        </div>
        <a className="download" href={`/api/artifacts/${result.csv_artifact_id}/download`}>
          {chinese ? "下载 CSV" : "Download CSV"}
        </a>
      </div>
      <div className="result-grid">
        <article className="analysis-card chart-card">
          <h3>{diagnosticHierarchy.length > 0
            ? (chinese ? "Agent 阶段对比" : "Agent-stage comparison")
            : result.chart.chart_type.replaceAll("_", " ")}</h3>
          <PlotlyFigure figure={result.chart.figure} />
          {result.chart.fallback_table ? (
            <p className="warning">{chinese ? "原图表不适合当前结果，已改用表格。" : "The requested chart was unsuitable; a table fallback was used."}</p>
          ) : null}
        </article>
        <article className="analysis-card evidence-card">
          <h3>{chinese ? "有依据的结论" : "Evidence-linked conclusions"}</h3>
          {result.computation.conclusions.map((item) => (
            <div className="conclusion" key={item.text}>
              <span className={`label label-${item.epistemic_label.toLowerCase().replace(" ", "-")}`}>
                {epistemicLabel(item.epistemic_label)}
              </span>
              <p>{item.text}</p>
              <small>{evidenceReference(item.evidence_ids)}</small>
            </div>
          ))}
        </article>
      </div>
      {diagnosticHierarchy.map((level) => (
        <article className="analysis-card" key={level.key}>
          <div className="card-heading">
            <h3>{level.label}{chinese ? "对比" : " comparison"}</h3>
            {Object.keys(level.parent).length > 0 ? (
              <span>{chinese ? "仅下钻：" : "Drill-down: "}{Object.values(level.parent).join(" / ")}</span>
            ) : null}
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{level.label}</th>
                  <th>{chinese ? "异常期日均" : "Incident daily avg"}</th>
                  <th>{chinese ? "基线日均" : "Baseline daily avg"}</th>
                  <th>{chinese ? "额外离开会话数" : "Excess failed sessions"}</th>
                  <th>{chinese ? "失败占比变化" : "Failure-share change"}</th>
                </tr>
              </thead>
              <tbody>
                {level.display_rows.map((row) => (
                  <tr key={row.value}>
                    <td>{row.value}</td>
                    <td>{formatNumber(row.incident_average_daily_count)}</td>
                    <td>{formatNumber(row.baseline_average_daily_count)}</td>
                    <td>{formatNumber(row.excess_failed_sessions)}</td>
                    <td>{(row.failure_share_change * 100).toFixed(1)} pp</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      ))}
      {responseEvidence ? (
        <article className="analysis-card response-evidence-card">
          <div className="card-heading">
            <div>
              <h3>{chinese ? "离开位置的 Bot 回复证据" : "Bot-response evidence at the exit location"}</h3>
              <p className="muted">
                {chinese ? "用于辅助人工判断问题场景，不把单条话术当作根因。" : "Use these samples for diagnosis; a single response does not prove root cause."}
              </p>
            </div>
            <span>{Object.values(responseEvidence.selected_path).join(" / ")}</span>
          </div>
          <div className="response-window-grid">
            {(["incident", "baseline"] as const).map((window) => (
              <section key={window}>
                <h4>{window === "incident"
                  ? (chinese ? "异常期样本" : "Incident samples")
                  : (chinese ? "基线样本" : "Baseline samples")}</h4>
                {responseEvidence.samples[window].length === 0 ? (
                  <p className="muted">{chinese ? "当前没有可用样本。" : "No sample is available."}</p>
                ) : responseEvidence.samples[window].map((sample, index) => (
                  <details className="response-sample" key={`${window}-${index}`}>
                    <summary>{sample.comparison_date ?? "—"} · {
                      [sample.agent_stage, sample.symptom, sample.flow_step]
                        .filter(Boolean).join(" / ")
                    }</summary>
                    <p>{sample.bot_response}</p>
                  </details>
                ))}
              </section>
            ))}
          </div>
        </article>
      ) : null}
      <article className="analysis-card">
        <div className="card-heading">
          <h3>{chinese ? "计算结果表" : "Result table"}</h3>
          <span>{displayRows.length} {chinese ? "行" : "rows"}</span>
        </div>
        <div className="table-scroll">
          <table aria-label={chinese ? "计算结果表" : "Result table"}>
            <thead>
              <tr>
                {displayColumns.map((column) => <th key={column}>{column}</th>)}
              </tr>
            </thead>
            <tbody>
              {displayRows.map((row, index) => (
                <tr key={index}>
                  {displayColumns.map((column) => (
                    <td
                      className={typeof row[column] === "string" && String(row[column]).length > 80 ? "long-text-cell" : undefined}
                      key={column}
                    >{String(row[column] ?? "—")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {finalDataset.quality.warnings.map((warning) => (
          <p className="warning" key={warning}>{warning}</p>
        ))}
      </article>
      {result.join_quality ? (
        <article className="analysis-card">
          <h3>{chinese ? "跨数据库关联质量" : "Cross-database join quality"}</h3>
          <pre>{JSON.stringify(result.join_quality, null, 2)}</pre>
        </article>
      ) : null}
      <article className="analysis-card">
        <h3>{chinese ? "依据明细" : "Evidence records"}</h3>
        <div className="evidence-list">
          {result.computation.evidence.map((item) => (
            <details key={item.id}>
              <summary>{(chinese ? "依据 " : "Evidence ") + evidenceLabels.get(item.id)} · {epistemicLabel(item.epistemic_label)} · {item.title}</summary>
              <p>{item.calculation}</p>
              <pre>{JSON.stringify(item.support, null, 2)}</pre>
              {item.limitations.map((limitation) => (
                <p className="warning" key={limitation}>{limitation}</p>
              ))}
            </details>
          ))}
        </div>
      </article>
    </section>
  );
}
