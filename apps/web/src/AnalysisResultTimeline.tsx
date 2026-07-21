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
          <h3>{chinese ? "Agent 阶段对比" : result.chart.chart_type.replaceAll("_", " ")}</h3>
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
      <article className="analysis-card">
        <div className="card-heading">
          <h3>{chinese ? "原始结果表" : "Result table"}</h3>
          <span>{finalDataset.row_count} {chinese ? "行" : "rows"}</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {finalDataset.columns.map((column) => <th key={column}>{column}</th>)}
              </tr>
            </thead>
            <tbody>
              {finalDataset.rows.map((row, index) => (
                <tr key={index}>
                  {finalDataset.columns.map((column) => (
                    <td key={column}>{String(row[column] ?? "—")}</td>
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
