import { ChangeEvent, useEffect, useState } from "react";
import {
  governanceApi,
  type DocumentView,
  type KnowledgeAnswer,
  type MemoryProposal,
  type MemoryView,
  type SkillProposal,
} from "./governanceApi";
import "./governance.css";

function locationLabel(location: KnowledgeAnswer["citations"][number]["location"]): string {
  return [
    location.page ? `page ${location.page}` : "",
    location.sheet ? `sheet ${location.sheet}` : "",
    location.section ? `section ${location.section}` : "",
    location.row_start ? `rows ${location.row_start}-${location.row_end ?? location.row_start}` : "",
    location.line_start ? `lines ${location.line_start}-${location.line_end ?? location.line_start}` : "",
  ].filter(Boolean).join(", ") || "document";
}

export function GovernanceCenter() {
  const [documents, setDocuments] = useState<DocumentView[]>([]);
  const [conflicts, setConflicts] = useState<Array<{ id: string; name: string; status: string }>>([]);
  const [skills, setSkills] = useState<SkillProposal[]>([]);
  const [memoryProposals, setMemoryProposals] = useState<MemoryProposal[]>([]);
  const [memories, setMemories] = useState<MemoryView[]>([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<KnowledgeAnswer | null>(null);
  const [teaching, setTeaching] = useState("");
  const [memoryKey, setMemoryKey] = useState("");
  const [memoryValue, setMemoryValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [nextDocuments, nextConflicts, nextSkills, nextMemoryProposals, nextMemories] =
      await Promise.all([
        governanceApi.documents(),
        governanceApi.conflicts(),
        governanceApi.skillProposals(),
        governanceApi.memoryProposals(),
        governanceApi.memories(),
      ]);
    setDocuments(nextDocuments);
    setConflicts(nextConflicts);
    setSkills(nextSkills);
    setMemoryProposals(nextMemoryProposals);
    setMemories(nextMemories);
  }

  useEffect(() => { void refresh().catch(() => undefined); }, []);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Governance action failed.");
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
    <section className="governance-center" aria-label="Knowledge, Skill, and Memory administration">
      <div className="governance-heading">
        <div><span className="eyebrow">Governed records</span><h2>Knowledge, Skill, and Memory</h2></div>
        <span className="policy-chip">Exact approval required</span>
      </div>
      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <div className="governance-grid">
        <article className="governance-panel governance-wide">
          <div className="panel-heading">
            <div><h3>Knowledge documents</h3><p>Review Agent proposals or upload an approved source document.</p></div>
            <label className="file-picker">Upload source<input type="file" accept=".pdf,.docx,.xlsx,.csv,.txt,.md,.markdown" onChange={upload} disabled={busy} /></label>
          </div>
          <div className="document-list">
            {documents.length === 0 ? <p>No documents yet.</p> : documents.map((document) => (
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

        <article className="governance-panel">
          <h3>Retrieval check</h3>
          <div className="inline-form"><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="How is Net Revenue defined?" /><button type="button" disabled={!question.trim() || busy} onClick={() => void act(async () => setAnswer(await governanceApi.ask(question)))}>Ask</button></div>
          {answer ? <div className="knowledge-answer"><span className={`label label-${answer.epistemic_label.toLowerCase().replace(" ", "-")}`}>{answer.epistemic_label}</span><p>{answer.answer}</p>{answer.citations.map((citation) => <details key={citation.chunk_id}><summary>{citation.filename} v{citation.version} · {locationLabel(citation.location)}</summary><p>{citation.excerpt}</p><small>Hybrid score {citation.score}</small></details>)}</div> : null}
        </article>

        <article className="governance-panel">
          <h3>Knowledge conflicts</h3>
          {conflicts.length === 0 ? <p>No open conflicts.</p> : <div className="conflict-box">{conflicts.map((item) => <p key={item.id}>{item.name} · {item.status} · owner confirmation required</p>)}</div>}
        </article>

        <article className="governance-panel governance-wide">
          <h3>Skill proposals</h3>
          <textarea value={teaching} onChange={(event) => setTeaching(event.target.value)} placeholder="Create a repeatable analysis method…" rows={3} />
          <button type="button" disabled={!teaching.trim() || busy} onClick={() => void act(async () => { await governanceApi.proposeSkill(teaching); setTeaching(""); })}>Create proposal</button>
          {skills.map((proposal) => <details className="proposal" key={proposal.id} open={proposal.status === "pending_approval"}><summary>{proposal.name} v{proposal.version} · {proposal.status}</summary><small>Allowed tools: {proposal.tool_allowlist.join(", ")}</small><pre>{JSON.stringify(proposal.diff, null, 2)}</pre><div className="approval-actions">{proposal.status === "pending_approval" ? <><button className="approve" type="button" onClick={() => void act(() => governanceApi.decideSkill(proposal, "approved"))}>Approve exact diff</button><button className="reject" type="button" onClick={() => void act(() => governanceApi.decideSkill(proposal, "rejected"))}>Reject</button></> : null}{proposal.status === "active" ? <button type="button" onClick={() => void act(() => governanceApi.skillLifecycle(proposal, "deprecate"))}>Deprecate</button> : null}{proposal.status === "deprecated" ? <button type="button" onClick={() => void act(() => governanceApi.skillLifecycle(proposal, "rollback"))}>Rollback to version</button> : null}</div><small className="hash">Exact diff: {proposal.payload_hash.slice(0, 20)}…</small></details>)}
        </article>

        <article className="governance-panel governance-wide">
          <h3>Long-term Memory</h3>
          <div className="memory-form"><input value={memoryKey} onChange={(event) => setMemoryKey(event.target.value)} placeholder="Memory key" /><input value={memoryValue} onChange={(event) => setMemoryValue(event.target.value)} placeholder="Explicit value (never secrets)" /><button type="button" disabled={!memoryKey.trim() || !memoryValue.trim() || busy} onClick={() => void act(async () => { await governanceApi.proposeMemory(memoryKey, memoryValue); setMemoryKey(""); setMemoryValue(""); })}>Propose</button></div>
          {memoryProposals.map((proposal) => <div className="memory-row" key={proposal.id}><div><strong>{proposal.scope} / {proposal.key}</strong><small>{proposal.status} · {proposal.source}</small></div>{proposal.status === "pending_approval" ? <div className="approval-actions"><button className="approve" type="button" onClick={() => void act(() => governanceApi.decideMemory(proposal, "approved"))}>Approve</button><button className="reject" type="button" onClick={() => void act(() => governanceApi.decideMemory(proposal, "rejected"))}>Reject</button></div> : null}</div>)}
          {memories.map((memory) => <div className="memory-row" key={memory.id}><div><strong>{memory.key} v{memory.version}</strong><small>{memory.scope} · {memory.status} · {JSON.stringify(memory.value)}</small></div>{memory.status === "active" ? <button type="button" onClick={() => void act(() => governanceApi.deleteMemory(memory.id))}>Delete</button> : null}</div>)}
        </article>
      </div>
    </section>
  );
}
