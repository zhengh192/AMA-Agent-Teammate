import { useEffect, useState } from "react";
import {
  governanceApi,
  type MemoryProposal,
  type MemoryView,
} from "../governanceApi";

export function MemoryAdminPage() {
  const [proposals, setProposals] = useState<MemoryProposal[]>([]);
  const [memories, setMemories] = useState<MemoryView[]>([]);
  const [memoryKey, setMemoryKey] = useState("");
  const [memoryValue, setMemoryValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [nextProposals, nextMemories] = await Promise.all([
      governanceApi.memoryProposals(),
      governanceApi.memories(),
    ]);
    setProposals(nextProposals);
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
      setError(caught instanceof Error ? caught.message : "Memory action failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="admin-page" aria-label="Memory administration">
      <div className="governance-heading">
        <div><span className="eyebrow">Governed assets</span><h2>Memory</h2><p>Keep only small, explicit, durable context that has a clear source, scope, owner, and lifecycle.</p></div>
        <span className="format-chip">scope + key + value + source</span>
      </div>
      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <article className="governance-panel memory-principles">
        <h3>What belongs here</h3>
        <div className="principle-grid"><p><strong>Good Memory</strong>Explicit preferences, stable project context, approved entity facts, with expiry where appropriate.</p><p><strong>Not Memory</strong>Secrets, raw conversation history, hidden inference, query exports, or facts better maintained as cited Knowledge.</p></div>
      </article>

      <div className="governance-grid">
        <article className="governance-panel">
          <h3>Pending proposals</h3>
          <div className="memory-form"><input value={memoryKey} onChange={(event) => setMemoryKey(event.target.value)} placeholder="Memory key" /><input value={memoryValue} onChange={(event) => setMemoryValue(event.target.value)} placeholder="Explicit value (never secrets)" /><button type="button" disabled={!memoryKey.trim() || !memoryValue.trim() || busy} onClick={() => void act(async () => { await governanceApi.proposeMemory(memoryKey, memoryValue); setMemoryKey(""); setMemoryValue(""); })}>Propose</button></div>
          {proposals.length === 0 ? <p>No Memory proposals.</p> : proposals.map((proposal) => <div className="memory-row" key={proposal.id}><div><strong>{proposal.scope} / {proposal.key}</strong><small>{proposal.status} · {proposal.source}</small><code>{JSON.stringify(proposal.value)}</code></div>{proposal.status === "pending_approval" ? <div className="approval-actions"><button className="approve" type="button" onClick={() => void act(() => governanceApi.decideMemory(proposal, "approved"))}>Approve exact record</button><button className="reject" type="button" onClick={() => void act(() => governanceApi.decideMemory(proposal, "rejected"))}>Reject</button></div> : null}</div>)}
        </article>

        <article className="governance-panel">
          <h3>Active Memory</h3>
          <p>Approved records available to later matching Agent runs.</p>
          {memories.length === 0 ? <p>No active Memory.</p> : memories.map((memory) => <div className="memory-row" key={memory.id}><div><strong>{memory.key} v{memory.version}</strong><small>{memory.scope} · {memory.status} · source: {memory.source}</small><code>{JSON.stringify(memory.value)}</code></div>{memory.status === "active" ? <button type="button" onClick={() => void act(() => governanceApi.deleteMemory(memory.id))}>Delete</button> : null}</div>)}
        </article>
      </div>
    </section>
  );
}
