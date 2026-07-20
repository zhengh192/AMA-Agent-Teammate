import { type ChangeEvent, type FormEvent, useEffect, useState } from "react";
import { ConfirmAction } from "./ConfirmAction";
import {
  governanceApi,
  type BusinessRuleView,
  type DocumentView,
  type KnowledgeAnswer,
  type KnowledgeEntryInput,
  type KnowledgeProposal,
  type LearnedMetricView,
} from "../governanceApi";

type KnowledgeDraft = Omit<KnowledgeEntryInput, "effective_date"> & { effective_date: string };

const EMPTY_DRAFT: KnowledgeDraft = {
  kind: "business_context",
  name: "",
  definition: "",
  owner: "Super Agent team",
  source: "explicit admin entry",
  effective_date: "",
};

function locationLabel(location: KnowledgeAnswer["citations"][number]["location"]): string {
  return [
    location.page ? `page ${location.page}` : "",
    location.sheet ? `sheet ${location.sheet}` : "",
    location.section ? `section ${location.section}` : "",
    location.row_start ? `rows ${location.row_start}-${location.row_end ?? location.row_start}` : "",
    location.line_start ? `lines ${location.line_start}-${location.line_end ?? location.line_start}` : "",
  ].filter(Boolean).join(", ") || "document";
}

function directEntry(document: DocumentView): KnowledgeEntryInput | null {
  const value = document.source_metadata.knowledge_entry;
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const entry = value as Partial<KnowledgeEntryInput>;
  if (!entry.kind || !entry.name || !entry.definition || !entry.owner || !entry.source) return null;
  return { ...entry, effective_date: entry.effective_date ?? null } as KnowledgeEntryInput;
}

export function KnowledgeAdminPage() {
  const [documents, setDocuments] = useState<DocumentView[]>([]);
  const [proposals, setProposals] = useState<KnowledgeProposal[]>([]);
  const [conflicts, setConflicts] = useState<Array<{ id: string; name: string; status: string }>>([]);
  const [learnedMetrics, setLearnedMetrics] = useState<LearnedMetricView[]>([]);
  const [businessRules, setBusinessRules] = useState<BusinessRuleView[]>([]);
  const [draft, setDraft] = useState<KnowledgeDraft>(EMPTY_DRAFT);
  const [editingDocumentId, setEditingDocumentId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<KnowledgeAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [nextDocuments, nextProposals, nextConflicts, nextLearnedMetrics, nextBusinessRules] =
      await Promise.all([
        governanceApi.documents(),
        governanceApi.knowledgeProposals(),
        governanceApi.conflicts(),
        governanceApi.learnedMetrics(),
        governanceApi.businessRules(),
      ]);
    setDocuments(nextDocuments);
    setProposals(nextProposals);
    setConflicts(nextConflicts);
    setLearnedMetrics(nextLearnedMetrics);
    setBusinessRules(nextBusinessRules);
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

  function resetDraft() {
    setDraft(EMPTY_DRAFT);
    setEditingDocumentId(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input: KnowledgeEntryInput = {
      ...draft,
      name: draft.name.trim(),
      definition: draft.definition.trim(),
      owner: draft.owner.trim(),
      source: draft.source.trim(),
      effective_date: draft.effective_date || null,
    };
    await act(async () => {
      if (editingDocumentId) await governanceApi.editKnowledge(editingDocumentId, input);
      else await governanceApi.proposeKnowledge(input);
      resetDraft();
    });
  }

  function editDocument(document: DocumentView) {
    const entry = directEntry(document);
    if (!entry) return;
    setEditingDocumentId(document.id);
    setDraft({ ...entry, effective_date: entry.effective_date ?? "" });
  }

  function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) void act(() => governanceApi.upload(file));
    event.target.value = "";
  }

  return (
    <section className="admin-page" aria-label="Knowledge administration">
      <div className="governance-heading">
        <div><span className="eyebrow">Governed assets</span><h2>Knowledge</h2><p>Add, revise, approve, and retire source-backed business context. Direct edits create an inert proposal; the active version changes only after exact approval.</p></div>
        <span className="format-chip">Versioned sources + citations</span>
      </div>
      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <article className="governance-panel governance-wide asset-editor">
        <div className="panel-heading">
          <div><h3>{editingDocumentId ? "Edit Knowledge" : "Add Knowledge"}</h3><p>Use this for durable business definitions or context. Files can still be uploaded in the source library below.</p></div>
          {editingDocumentId ? <button type="button" onClick={resetDraft}>Cancel edit</button> : null}
        </div>
        <form className="asset-editor-form" onSubmit={(event) => void submit(event)}>
          <label>Type<select value={draft.kind} onChange={(event) => setDraft({ ...draft, kind: event.target.value as KnowledgeEntryInput["kind"] })}><option value="business_context">Business context</option><option value="metric">Metric definition</option><option value="data_source">Data source</option><option value="table">Table definition</option><option value="field">Field definition</option><option value="business_rule">Business rule</option><option value="process">Process</option></select></label>
          <label>Name<input aria-label="Knowledge name" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
          <label className="asset-editor-wide">Definition<textarea aria-label="Knowledge definition" rows={5} value={draft.definition} onChange={(event) => setDraft({ ...draft, definition: event.target.value })} /></label>
          <label>Owner<input aria-label="Knowledge owner" value={draft.owner} onChange={(event) => setDraft({ ...draft, owner: event.target.value })} /></label>
          <label>Source<input aria-label="Knowledge source" value={draft.source} onChange={(event) => setDraft({ ...draft, source: event.target.value })} /></label>
          <label>Effective date<input type="date" value={draft.effective_date} onChange={(event) => setDraft({ ...draft, effective_date: event.target.value })} /></label>
          <div className="asset-editor-actions"><button className="approve" type="submit" disabled={busy || !draft.name.trim() || !draft.definition.trim() || !draft.owner.trim() || !draft.source.trim()}>{editingDocumentId ? "Create revision proposal" : "Create proposal"}</button></div>
        </form>
      </article>

      <article className="governance-panel governance-wide">
        <div className="panel-heading"><div><h3>Knowledge change proposals</h3><p>Approve or reject the exact version. Delete proposals are also approval-gated.</p></div><span className="format-chip">{proposals.filter((item) => item.status === "pending_approval").length} waiting</span></div>
        <div className="document-list">
          {proposals.length === 0 ? <p>No Knowledge change proposals.</p> : proposals.map((proposal) => (
            <details className="document-row" key={proposal.id} open={proposal.status === "pending_approval"}>
              <summary>{proposal.action.toUpperCase()} · {proposal.payload.name ?? proposal.filename} · {proposal.status}</summary>
              {proposal.payload.definition ? <p>{proposal.payload.definition}</p> : <p>This proposal retires the active source after approval.</p>}
              <small>Base version: {proposal.base_version ?? "new"} · Exact payload: {proposal.payload_hash.slice(0, 20)}…</small>
              <div className="approval-actions">
                {proposal.status === "pending_approval" ? <><button className="approve" type="button" disabled={busy} onClick={() => void act(() => governanceApi.decideKnowledge(proposal, "approved"))}>Approve exact change</button><button className="reject" type="button" disabled={busy} onClick={() => void act(() => governanceApi.decideKnowledge(proposal, "rejected"))}>Reject</button></> : null}
                {proposal.status !== "approved" && proposal.status !== "deleted" ? <ConfirmAction label="Delete proposal" message="Delete this proposal history?" disabled={busy} onConfirm={() => void act(() => governanceApi.deleteKnowledgeProposal(proposal.id))} /> : null}
              </div>
            </details>
          ))}
        </div>
      </article>

      <div className="governance-grid">
        <article className="governance-panel governance-wide">
          <div className="panel-heading">
            <div><h3>Source library</h3><p>Approved sources available to retrieval. Direct entries can be revised here; all sources can be retired through a confirmed proposal.</p></div>
            <label className="file-picker">Upload source<input type="file" accept=".pdf,.docx,.xlsx,.csv,.txt,.md,.markdown" onChange={upload} disabled={busy} /></label>
          </div>
          <div className="document-list">
            {documents.length === 0 ? <p>No Knowledge sources yet.</p> : documents.map((document) => (
              <details className="document-row" key={document.id} open={document.status === "pending_approval"}>
                <summary>{document.filename} · v{document.version} · {document.status}</summary>
                <p>{document.preview || "No preview available."}</p>
                <small>Parser: {document.parser_status} · {document.chunks} chunks · Hash: {document.content_hash.slice(0, 20)}…</small>
                <div className="approval-actions">
                  {document.status === "pending_approval" ? <><button className="approve" type="button" onClick={() => void act(() => governanceApi.decideDocument(document, "approved"))}>Approve exact document</button><button className="reject" type="button" onClick={() => void act(() => governanceApi.decideDocument(document, "rejected"))}>Reject</button></> : null}
                  {document.status === "active" && directEntry(document) ? <button type="button" onClick={() => editDocument(document)}>Edit</button> : null}
                  {document.status === "active" ? <ConfirmAction label="Delete" message={`Retire ${document.filename}? The source will stop influencing the Agent after proposal approval.`} disabled={busy} onConfirm={() => void act(() => governanceApi.proposeKnowledgeDelete(document.id))} /> : null}
                </div>
              </details>
            ))}
          </div>
        </article>

        <article className="governance-panel governance-wide">
          <div className="panel-heading"><div><h3>Learned metric definitions</h3><p>Definitions explicitly confirmed in Agent conversations remain visible and versioned.</p></div><span className="format-chip">{learnedMetrics.length} active</span></div>
          <div className="document-list">{learnedMetrics.length === 0 ? <p>No learned metrics yet.</p> : learnedMetrics.map((metric) => <details className="document-row" key={metric.id}><summary>{metric.display_name} · v{metric.version} · {metric.status}</summary><p>{metric.definition.aggregation}({metric.definition.value_field}) from {metric.definition.table}; time field {metric.definition.time_field}</p><small>Aliases: {metric.aliases.join(", ") || "none"} · Source: {metric.source}</small></details>)}</div>
        </article>

        <article className="governance-panel governance-wide">
          <div className="panel-heading"><div><h3>Active business rules</h3><p>Authoritative semantic boundaries loaded from the version-controlled metadata registry.</p></div><span className="format-chip">{businessRules.length} active</span></div>
          <div className="document-list">{businessRules.length === 0 ? <p>No active business rules.</p> : businessRules.map((rule) => <details className="document-row" key={rule.id} open={rule.id === "super_agent.valid_user_traffic_population"}><summary>{rule.name} · {rule.id}@{rule.version} · {rule.severity}</summary><p>{rule.statement}</p>{rule.expression ? <pre>{rule.expression}</pre> : null}<small>Applies to: {rule.applies_to.join(", ")} · Owner: {rule.owner} · Source: {rule.source}</small></details>)}</div>
        </article>

        <article className="governance-panel"><h3>Retrieval check</h3><p>Verify what the Agent can support from currently active Knowledge.</p><div className="inline-form"><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="How is Net Revenue defined?" /><button type="button" disabled={!question.trim() || busy} onClick={() => void act(async () => setAnswer(await governanceApi.ask(question)))}>Ask</button></div>{answer ? <div className="knowledge-answer"><span className={`label label-${answer.epistemic_label.toLowerCase().replace(" ", "-")}`}>{answer.epistemic_label}</span><p>{answer.answer}</p>{answer.citations.map((citation) => <details key={citation.chunk_id}><summary>{citation.filename} v{citation.version} · {locationLabel(citation.location)}</summary><p>{citation.excerpt}</p><small>Hybrid score {citation.score}</small></details>)}</div> : null}</article>
        <article className="governance-panel"><h3>Definition conflicts</h3><p>Conflicting active definitions require an owner decision; the Agent will not silently merge them.</p>{conflicts.length === 0 ? <p>No open conflicts.</p> : <div className="conflict-box">{conflicts.map((item) => <p key={item.id}>{item.name} · {item.status} · owner confirmation required</p>)}</div>}</article>
      </div>
    </section>
  );
}