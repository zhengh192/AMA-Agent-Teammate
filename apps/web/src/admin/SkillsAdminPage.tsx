import { useEffect, useState } from "react";
import { governanceApi, type AnalysisSkillView, type SkillProposal } from "../governanceApi";

function renderFile(content: unknown): string {
  return typeof content === "string" ? content : JSON.stringify(content, null, 2);
}

export function SkillsAdminPage() {
  const [skills, setSkills] = useState<SkillProposal[]>([]);
  const [installedSkills, setInstalledSkills] = useState<AnalysisSkillView[]>([]);
  const [teaching, setTeaching] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [installed, proposals] = await Promise.all([
      governanceApi.analysisSkills(),
      governanceApi.skillProposals(),
    ]);
    setInstalledSkills(installed);
    setSkills(proposals);
  }
  useEffect(() => {
    void refresh().catch((caught) => {
      setError(caught instanceof Error ? caught.message : "Skill registry failed to load.");
    });
  }, []);

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


      <article className="governance-panel installed-skill-panel">
        <div className="panel-heading">
          <div><h3>Installed analysis skills</h3><p>Validated Git-tracked packages currently available to the analysis planner.</p></div>
          <span className="format-chip">{installedSkills.length} packages</span>
        </div>
        <div className="installed-skill-list">
          {installedSkills.length === 0 ? <p>No installed analysis skills.</p> : installedSkills.map((skill) => (
            <details className="installed-skill" key={`${skill.id}@${skill.version}`}>
              <summary><span>{skill.name}</span><small>v{skill.version} � {skill.status}</small></summary>
              <p>{skill.description}</p>
              <dl className="skill-metadata-grid">
                <div><dt>Registry ID</dt><dd><code>{skill.id}</code></dd></div>
                <div><dt>Owner</dt><dd>{skill.owner}</dd></div>
                <div><dt>Risk</dt><dd>{skill.risk_level}</dd></div>
                <div><dt>Approval</dt><dd>{skill.approval.required ? "Required" : "Not required"}</dd></div>
                <div><dt>Analysis intents</dt><dd>{skill.analysis_intents.join(", ")}</dd></div>
                <div><dt>Prerequisites</dt><dd>{skill.prerequisite_skills.join(", ") || "None"}</dd></div>
                <div><dt>Required metadata</dt><dd>{skill.required_metadata.join(", ") || "None"}</dd></div>
                <div><dt>Tools</dt><dd>{skill.required_tools.join(", ") || "Controlled library only"}</dd></div>
              </dl>
              {skill.deterministic_operations.length > 0 ? (
                <div className="skill-operations"><strong>Deterministic operations</strong><span>{skill.deterministic_operations.join(", ")}</span></div>
              ) : null}
            </details>
          ))}
        </div>
      </article>

      <article className="governance-panel skill-list-panel">
        <div className="panel-heading"><div><h3>Taught skill proposals</h3><p>Teach in the Agent or draft here. Only an exact approved package can become active.</p></div></div>
        <textarea value={teaching} onChange={(event) => setTeaching(event.target.value)} placeholder="Create a repeatable analysis method…" rows={3} />
        <button type="button" disabled={!teaching.trim() || busy} onClick={() => void act(async () => { await governanceApi.proposeSkill(teaching); setTeaching(""); })}>Create draft package</button>
        <div className="skill-list">
          {skills.length === 0 ? <p>No taught skill proposals yet.</p> : skills.map((proposal) => (
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
