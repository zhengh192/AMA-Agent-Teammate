import { useEffect, useState } from "react";
import { governanceApi, type SkillProposal } from "../governanceApi";

function renderFile(content: unknown): string {
  return typeof content === "string" ? content : JSON.stringify(content, null, 2);
}

export function SkillsAdminPage() {
  const [skills, setSkills] = useState<SkillProposal[]>([]);
  const [teaching, setTeaching] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() { setSkills(await governanceApi.skillProposals()); }
  useEffect(() => { void refresh().catch(() => undefined); }, []);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Skill action failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="admin-page" aria-label="Skills administration">
      <div className="governance-heading">
        <div><span className="eyebrow">Governed assets</span><h2>Skills</h2><p>Turn repeatable working methods into versioned, testable, Git-tracked capability packages.</p></div>
        <span className="format-chip">SKILL.md + metadata.yaml</span>
      </div>
      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <article className="governance-panel skill-standard">
        <h3>Package contract</h3>
        <div className="package-tree"><code>skill-name/version/</code><code>├─ SKILL.md</code><code>├─ metadata.yaml</code><code>├─ examples/example.md</code><code>└─ tests/test_cases.yaml</code></div>
        <p><strong>SKILL.md</strong> contains the approved operating instructions. Metadata declares version, owner, permissions, tool allowlist, inputs/outputs, and rollback. Examples and tests make the method reviewable before activation.</p>
      </article>

      <article className="governance-panel skill-list-panel">
        <div className="panel-heading"><div><h3>Skill registry</h3><p>Teach in the Agent or draft here. Only an exact approved package is discoverable at runtime.</p></div></div>
        <textarea value={teaching} onChange={(event) => setTeaching(event.target.value)} placeholder="Create a repeatable analysis method…" rows={3} />
        <button type="button" disabled={!teaching.trim() || busy} onClick={() => void act(async () => { await governanceApi.proposeSkill(teaching); setTeaching(""); })}>Create draft package</button>
        <div className="skill-list">
          {skills.length === 0 ? <p>No Skill packages yet.</p> : skills.map((proposal) => (
            <details className="proposal" key={proposal.id} open={proposal.status === "pending_approval"}>
              <summary>{proposal.name} v{proposal.version} · {proposal.status}</summary>
              <div className="proposal-meta"><span>Tools: {proposal.tool_allowlist.join(", ")}</span><span>Exact package: {proposal.payload_hash.slice(0, 20)}…</span></div>
              <div className="package-files">{Object.entries(proposal.diff).map(([path, content]) => <details key={path} open={path === "SKILL.md"}><summary><code>{path}</code></summary><pre>{renderFile(content)}</pre></details>)}</div>
              <div className="approval-actions">
                {proposal.status === "pending_approval" ? <><button className="approve" type="button" onClick={() => void act(() => governanceApi.decideSkill(proposal, "approved"))}>Approve exact package</button><button className="reject" type="button" onClick={() => void act(() => governanceApi.decideSkill(proposal, "rejected"))}>Reject</button></> : null}
                {proposal.status === "active" ? <button type="button" onClick={() => void act(() => governanceApi.skillLifecycle(proposal, "deprecate"))}>Deprecate</button> : null}
                {proposal.status === "deprecated" ? <button type="button" onClick={() => void act(() => governanceApi.skillLifecycle(proposal, "rollback"))}>Rollback to version</button> : null}
              </div>
            </details>
          ))}
        </div>
      </article>
    </section>
  );
}
