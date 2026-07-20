import { type FormEvent, useEffect, useMemo, useState } from "react";
import { ConfirmAction } from "./ConfirmAction";
import {
  governanceApi,
  type MemoryInput,
  type MemoryProposal,
  type MemoryView,
} from "../governanceApi";

type MemoryDraft = {
  scope: MemoryInput["scope"];
  key: string;
  value: string;
  source: string;
  expiresAt: string;
};

const EMPTY_DRAFT: MemoryDraft = {
  scope: "project",
  key: "",
  value: "",
  source: "explicit admin entry",
  expiresAt: "",
};

function valueText(value: Record<string, unknown>): string {
  return typeof value.text === "string" ? value.text : JSON.stringify(value, null, 2);
}

function valuePayload(value: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (trimmed.startsWith("{")) {
    try {
      const parsed = JSON.parse(trimmed) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      // Plain text is a valid Memory value; malformed JSON is kept as text.
    }
  }
  return { text: trimmed };
}

function dateLabel(value: string | null): string {
  if (!value) return "No expiry";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function toLocalDateTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

export function MemoryAdminPage() {
  const [proposals, setProposals] = useState<MemoryProposal[]>([]);
  const [memories, setMemories] = useState<MemoryView[]>([]);
  const [draft, setDraft] = useState<MemoryDraft>(EMPTY_DRAFT);
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const pendingCount = useMemo(
    () => proposals.filter((proposal) => proposal.status === "pending_approval").length,
    [proposals],
  );
  const activeCount = useMemo(
    () => memories.filter((memory) => memory.status === "active").length,
    [memories],
  );

  async function refresh() {
    const [nextProposals, nextMemories] = await Promise.all([
      governanceApi.memoryProposals(),
      governanceApi.memories(),
    ]);
    setProposals(nextProposals);
    setMemories(nextMemories);
  }

  useEffect(() => {
    void refresh()
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Memory could not be loaded.");
      })
      .finally(() => setLoading(false));
  }, []);

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

  function resetDraft() {
    setDraft(EMPTY_DRAFT);
    setEditingMemoryId(null);
  }

  function editMemory(memory: MemoryView) {
    setEditingMemoryId(memory.id);
    setDraft({
      scope: memory.scope as MemoryInput["scope"],
      key: memory.key,
      value: valueText(memory.value),
      source: `explicit admin correction of ${memory.key} v${memory.version}`,
      expiresAt: toLocalDateTime(memory.expires_at),
    });
  }

  function useProposalAsDraft(proposal: MemoryProposal) {
    setEditingMemoryId(null);
    setDraft({
      scope: proposal.scope as MemoryInput["scope"],
      key: proposal.key,
      value: valueText(proposal.value),
      source: `revised from proposal ${proposal.id}`,
      expiresAt: toLocalDateTime(proposal.expires_at),
    });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const expiresAt = draft.expiresAt ? new Date(draft.expiresAt).toISOString() : null;
    const input: MemoryInput = {
      scope: draft.scope,
      key: draft.key.trim(),
      value: valuePayload(draft.value),
      source: draft.source.trim(),
      expires_at: expiresAt,
    };
    await act(async () => {
      if (editingMemoryId) {
        await governanceApi.editMemory(editingMemoryId, {
          value: input.value,
          source: input.source,
          expires_at: input.expires_at,
        });
      } else {
        await governanceApi.proposeMemory(input);
      }
      resetDraft();
    });
  }

  return (
    <section className="admin-page" aria-label="Memory administration">
      <div className="governance-heading">
        <div>
          <span className="eyebrow">Governed durable context</span>
          <h2>Memory</h2>
          <p>Review what the Agent may remember across conversations. Every addition or edit remains a proposal until you approve its exact payload.</p>
        </div>
        <span className="format-chip">{activeCount} active · {pendingCount} waiting</span>
      </div>
      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <article className="governance-panel memory-editor">
        <div className="panel-heading">
          <div>
            <h3>{editingMemoryId ? "Edit Memory" : "Add Memory"}</h3>
            <p>{editingMemoryId ? "Saving creates a new version proposal; the active version stays in use until approval." : "Create a reviewable proposal from explicit durable context. It is inert until approved."}</p>
          </div>
          {editingMemoryId ? <button type="button" onClick={resetDraft}>Cancel edit</button> : null}
        </div>
        <form className="memory-editor-form" onSubmit={(event) => void submit(event)}>
          <label>Scope<select aria-label="Memory scope" value={draft.scope} disabled={Boolean(editingMemoryId)} onChange={(event) => setDraft({ ...draft, scope: event.target.value as MemoryInput["scope"] })}><option value="project">Project</option><option value="user_preference">User preference</option><option value="entity">Entity</option><option value="session">Session</option></select></label>
          <label>Key<input aria-label="Memory key" value={draft.key} disabled={Boolean(editingMemoryId)} onChange={(event) => setDraft({ ...draft, key: event.target.value })} placeholder="e.g. default_jira_project" /></label>
          <label className="memory-value-field">Value<textarea aria-label="Memory value" rows={4} value={draft.value} onChange={(event) => setDraft({ ...draft, value: event.target.value })} placeholder="Plain text or a JSON object. Never enter passwords, tokens, or secrets." /></label>
          <label>Source<input aria-label="Memory source" value={draft.source} onChange={(event) => setDraft({ ...draft, source: event.target.value })} placeholder="Why this is authoritative" /></label>
          <label>Expires at (optional)<input aria-label="Memory expiry" type="datetime-local" value={draft.expiresAt} onChange={(event) => setDraft({ ...draft, expiresAt: event.target.value })} /></label>
          <div className="memory-editor-actions"><button className="approve" type="submit" disabled={!draft.key.trim() || !draft.value.trim() || !draft.source.trim() || busy}>{editingMemoryId ? "Save version proposal" : "Add proposal"}</button></div>
        </form>
      </article>

      <article className="governance-panel memory-principles">
        <h3>What belongs here</h3>
        <div className="principle-grid"><p><strong>Good Memory</strong>Explicit preferences, stable project context, approved entity facts, and expiry-aware temporary context.</p><p><strong>Not Memory</strong>Secrets, raw chat history, hidden inference, query exports, metric formulas, or facts better maintained as cited Knowledge.</p></div>
      </article>

      <div className="governance-grid memory-grid">
        <article className="governance-panel">
          <div className="panel-heading"><div><h3>Proposals</h3><p>Conversation-derived, imported, added, and edited candidates are all visible here.</p></div><span className="memory-count">{proposals.length}</span></div>
          {loading ? <p>Loading Memory proposals…</p> : proposals.length === 0 ? <p>No Memory proposals.</p> : proposals.map((proposal) => (
            <div className="memory-row" key={proposal.id}>
              <div className="memory-content"><div className="memory-title"><strong>{proposal.scope} / {proposal.key}</strong><span className={`memory-status ${proposal.status}`}>{proposal.status}</span></div><small>source: {proposal.source} · created: {dateLabel(proposal.created_at)} · expires: {dateLabel(proposal.expires_at)}</small><pre>{JSON.stringify(proposal.value, null, 2)}</pre></div>
              <div className="approval-actions">
                {proposal.status === "pending_approval" ? <><button className="approve" type="button" disabled={busy} onClick={() => void act(() => governanceApi.decideMemory(proposal, "approved"))}>Approve exact record</button><button className="reject" type="button" disabled={busy} onClick={() => void act(() => governanceApi.decideMemory(proposal, "rejected"))}>Reject</button></> : null}
                <button type="button" disabled={busy} onClick={() => useProposalAsDraft(proposal)}>Use as draft</button>
                {proposal.status !== "active" && proposal.status !== "deleted" ? <ConfirmAction label="Delete proposal" message="Delete this Memory proposal content?" disabled={busy} onConfirm={() => void act(() => governanceApi.deleteMemoryProposal(proposal.id))} /> : null}
              </div>
            </div>
          ))}
        </article>

        <article className="governance-panel">
          <div className="panel-heading"><div><h3>Memory versions</h3><p>Only records marked active are available to matching Agent runs; older lifecycle states remain visible.</p></div><span className="memory-count">{memories.length}</span></div>
          {!loading && activeCount === 0 ? <p>No active Memory.</p> : null}
          {loading ? <p>Loading Memory versions…</p> : memories.length === 0 ? <p>No Memory versions yet.</p> : memories.map((memory) => (
            <div className="memory-row" key={memory.id}>
              <div className="memory-content"><div className="memory-title"><strong>{memory.key} v{memory.version}</strong><span className={`memory-status ${memory.status}`}>{memory.status}</span></div><small>{memory.scope} · source: {memory.source} · created: {dateLabel(memory.created_at)} · expires: {dateLabel(memory.expires_at)}</small><pre>{JSON.stringify(memory.value, null, 2)}</pre></div>
              <div className="approval-actions"><button type="button" disabled={busy || memory.status === "deleted"} onClick={() => editMemory(memory)}>Edit</button>{memory.status === "active" ? <ConfirmAction label="Delete / forget" message={`Permanently forget ${memory.key} v${memory.version}? The stored value will be erased.`} disabled={busy} onConfirm={() => void act(() => governanceApi.deleteMemory(memory.id))} /> : null}</div>
            </div>
          ))}
        </article>
      </div>
    </section>
  );
}
