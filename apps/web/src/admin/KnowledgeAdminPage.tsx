import { type ChangeEvent, useEffect, useState } from "react";
import {
  governanceApi,
  type DocumentView,
  type KnowledgeAnswer,
  type LearnedMetricView,
} from "../governanceApi";

function locationLabel(location: KnowledgeAnswer["citations"][number]["location"]): string {
  return [
    location.page ? `page ${location.page}` : "",
    location.sheet ? `sheet ${location.sheet}` : "",
    location.section ? `section ${location.section}` : "",
    location.row_start ? `rows ${location.row_start}-${location.row_end ?? location.row_start}` : "",
    location.line_start ? `lines ${location.line_start}-${location.line_end ?? location.line_start}` : "",
  ].filter(Boolean).join(", ") || "document";
}

export function KnowledgeAdminPage() {
  const [documents, setDocuments] = useState<DocumentView[]>([]);
  const [conflicts, setConflicts] = useState<Array<{ id: string; name: string; status: string }>>([]);
  const [learnedMetrics, setLearnedMetrics] = useState<LearnedMetricView[]>([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<KnowledgeAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [nextDocuments, nextConflicts, nextLearnedMetrics] = await Promise.all([
      governanceApi.documents(),
      governanceApi.conflicts(),
      governanceApi.learnedMetrics(),
    ]);
    setDocuments(nextDocuments);
    setConflicts(nextConflicts);
    setLearnedMetrics(nextLearnedMetrics);
  }

  useEffect(() => { void refresh().catch(() => undefined); }, []);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Knowledge action failed.");
    } finally {
      setBusy(false);
    }
  }

  function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) void act(() => governanceApi.upload(file));
    event.target.value = "";
  }

  return (
    <section className="admin-page" aria-label="Knowledge administration">
      <div className="governance-heading">
        <div><span className="eyebrow">Governed assets</span><h2>Knowledge</h2><p>Accumulate source-backed definitions, rules, processes, and business context with precise citations.</p></div>
        <span className="format-chip">Documents + metadata + citations</span>
      </div>
      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <div className="governance-grid">
        <article className="governance-panel governance-wide">
          <div className="panel-heading">
            <div><h3>Source library</h3><p>Agent proposals arrive pending approval. Direct uploads are approved sources in this local pilot.</p></div>
            <label className="file-picker">Upload source<input type="file" accept=".pdf,.docx,.xlsx,.csv,.txt,.md,.markdown" onChange={upload} disabled={busy} /></label>
          </div>
          <div className="document-list">
            {documents.length === 0 ? <p>No Knowledge sources yet.</p> : documents.map((document) => (
              <details className="document-row" key={document.id} open={document.status === "pending_approval"}>
                <summary>{document.filename} · v{document.version} · {document.status}</summary>
                <p>{document.preview || "No preview available."}</p>
                <small>Parser: {document.parser_status} · {document.chunks} chunks · Hash: {document.content_hash.slice(0, 20)}…</small>
                {document.status === "pending_approval" ? <div className="approval-actions">
                  <button className="approve" type="button" onClick={() => void act(() => governanceApi.decideDocument(document, "approved"))}>Approve exact document</button>
                  <button className="reject" type="button" onClick={() => void act(() => governanceApi.decideDocument(document, "rejected"))}>Reject</button>
                </div> : null}
              </details>
            ))}
          </div>
        </article>

        <article className="governance-panel governance-wide">
          <div className="panel-heading">
            <div><h3>Learned metric definitions</h3><p>Definitions explicitly confirmed in Agent conversations are versioned here and reused before asking again.</p></div>
            <span className="format-chip">{learnedMetrics.length} active</span>
          </div>
          <div className="document-list">
            {learnedMetrics.length === 0 ? <p>No learned metrics yet. Ask the Agent for an undefined Super Agent metric and teach it the table and fields.</p> : learnedMetrics.map((metric) => (
              <details className="document-row" key={metric.id}>
                <summary>{metric.display_name} · v{metric.version} · {metric.status}</summary>
                <p>{metric.definition.aggregation}({metric.definition.value_field}) from {metric.definition.table}; time field {metric.definition.time_field}</p>
                <small>Aliases: {metric.aliases.join(", ") || "none"} · Source: {metric.source}</small>
                {metric.definition.filters.length ? <pre>{JSON.stringify({ filters: metric.definition.filters }, null, 2)}</pre> : null}
                {metric.definition.numerator_filters.length ? <pre>{JSON.stringify({ numerator: metric.definition.numerator_filters, denominator: metric.definition.denominator_filters }, null, 2)}</pre> : null}
              </details>
            ))}
          </div>
        </article>
        <article className="governance-panel">
          <h3>Retrieval check</h3>
          <p>Verify what the Agent can support from currently active Knowledge.</p>
          <div className="inline-form"><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="How is Net Revenue defined?" /><button type="button" disabled={!question.trim() || busy} onClick={() => void act(async () => setAnswer(await governanceApi.ask(question)))}>Ask</button></div>
          {answer ? <div className="knowledge-answer"><span className={`label label-${answer.epistemic_label.toLowerCase().replace(" ", "-")}`}>{answer.epistemic_label}</span><p>{answer.answer}</p>{answer.citations.map((citation) => <details key={citation.chunk_id}><summary>{citation.filename} v{citation.version} · {locationLabel(citation.location)}</summary><p>{citation.excerpt}</p><small>Hybrid score {citation.score}</small></details>)}</div> : null}
        </article>

        <article className="governance-panel">
          <h3>Definition conflicts</h3>
          <p>Conflicting active definitions require an owner decision; the Agent will not silently merge them.</p>
          {conflicts.length === 0 ? <p>No open conflicts.</p> : <div className="conflict-box">{conflicts.map((item) => <p key={item.id}>{item.name} · {item.status} · owner confirmation required</p>)}</div>}
        </article>
      </div>
    </section>
  );
}
