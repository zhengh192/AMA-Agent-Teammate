import type { AnalysisResult } from "./analysisTypes";
import { PlotlyFigure } from "./PlotlyFigure";

interface AnalysisResultTimelineProps {
  result: AnalysisResult;
}

export function AnalysisResultTimeline({ result }: AnalysisResultTimelineProps) {
  const finalDataset = result.datasets.at(-1) ?? null;
  if (!finalDataset) return null;

  return (
    <section
      className="analysis-results timeline-result"
      aria-label="Analysis results"
      data-run-id={result.run_id}
    >
      <div className="result-toolbar">
        <div>
          <span className="eyebrow">Completed</span>
          <h2>Bounded analysis result</h2>
        </div>
        <a className="download" href={`/api/artifacts/${result.csv_artifact_id}/download`}>
          Download CSV
        </a>
      </div>
      <div className="result-grid">
        <article className="analysis-card chart-card">
          <h3>{result.chart.chart_type.replaceAll("_", " ")}</h3>
          <PlotlyFigure figure={result.chart.figure} />
          {result.chart.fallback_table ? (
            <p className="warning">The requested chart was unsuitable; a table fallback was used.</p>
          ) : null}
        </article>
        <article className="analysis-card evidence-card">
          <h3>Evidence-linked conclusions</h3>
          {result.computation.conclusions.map((item) => (
            <div className="conclusion" key={item.text}>
              <span className={`label label-${item.epistemic_label.toLowerCase().replace(" ", "-")}`}>
                {item.epistemic_label}
              </span>
              <p>{item.text}</p>
              <small>Evidence: {item.evidence_ids.join(", ")}</small>
            </div>
          ))}
        </article>
      </div>
      <article className="analysis-card">
        <div className="card-heading">
          <h3>Result table</h3>
          <span>{finalDataset.row_count} rows</span>
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
          <h3>Cross-database join quality</h3>
          <pre>{JSON.stringify(result.join_quality, null, 2)}</pre>
        </article>
      ) : null}
      <article className="analysis-card">
        <h3>Evidence records</h3>
        <div className="evidence-list">
          {result.computation.evidence.map((item) => (
            <details key={item.id}>
              <summary>{item.epistemic_label} · {item.title}</summary>
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