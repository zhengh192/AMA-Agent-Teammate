import { useEffect, useState } from "react";
import { ConfirmAction } from "./ConfirmAction";
import { governanceApi, type AnalysisSkillView, type SkillProposal } from "../governanceApi";

function renderFile(content: unknown): string {
  return typeof content === "string" ? content : JSON.stringify(content, null, 2);
}

function starterMetadata(): Record<string, unknown> {
  const now = new Date().toISOString();
  return {
    id: "new_analysis_skill",
    name: "New Analysis Skill",
    version: "1.0.0",
    status: "active",
    description: "Describe the repeatable analytical method and when it should be selected.",
    owner: "Super Agent Data and Operations",
    reviewer: "Data Governance",
    created_at: now,
    updated_at: now,
    effective_from: now.slice(0, 10),
    effective_to: null,
    aliases: [],
    trigger_examples: { en: ["Example analytical request"], zh: ["示例分析请求"] },
    analysis_intents: ["trend"],
    required_metadata: ["dataset", "field"],
    prerequisite_skills: [],
    inputs: [{ name: "analysis_request", type: "string", required: true, description: "The scoped user request." }],
    outputs: [{ name: "analysis_result", type: "analysis_result", description: "Evidence-linked analytical result." }],
    required_tools: ["controlled_analysis_library"],
    deterministic_operations: [],
    risk_level: "medium",
    approval: { required: false, reason: null },
  };
}

export function SkillsAdminPage() {
  const [proposals, setProposals] = useState<SkillProposal[]>([]);
  const [installedSkills, setInstalledSkills] = useState<AnalysisSkillView[]>([]);
  const [teaching, setTeaching] = useState("");
  const [revisionProposal, setRevisionProposal] = useState<SkillProposal | null>(null);
  const [editingSkillId, setEditingSkillId] = useState<string | null>(null);
  const [metadataText, setMetadataText] = useState("");
  const [instructions, setInstructions] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [installed, nextProposals] = await Promise.all([
      governanceApi.analysisSkills(),
      governanceApi.skillProposals(),
    ]);
    setInstalledSkills(installed);
    setProposals(nextProposals);
  }

  useEffect(() => {
    void refresh().catch((caught) => setError(caught instanceof Error ? caught.message : "Skill registry failed to load."));
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

  function resetPackageEditor() {
    setEditingSkillId(null);
    setMetadataText("");
    setInstructions("");
  }

  function startNewSkill() {
    setEditingSkillId("new");
    setMetadataText(JSON.stringify(starterMetadata(), null, 2));
    setInstructions("# New Analysis Skill\n\nDescribe the repeatable method as concise imperative steps.\n");
  }

  async function startEditSkill(skillId: string) {
    setBusy(true);
    setError(null);
    try {
      const detail = await governanceApi.analysisSkill(skillId);
      const { instructions: body, path: _path, ...metadata } = detail;
      setEditingSkillId(skillId);
      setMetadataText(JSON.stringify(metadata, null, 2));
      setInstructions(body);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Skill could not be opened.");
    } finally {
      setBusy(false);
    }
  }

  async function submitPackage() {
    let metadata: unknown;
    try {
      metadata = JSON.parse(metadataText);
    } catch {
      setError("Metadata must be valid JSON. The API will then validate the strict Skill schema.");
      return;
    }
    if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
      setError("Metadata must be a JSON object.");
      return;
    }
    await act(async () => {
      await governanceApi.proposeAnalysisSkill(metadata as Record<string, unknown>, instructions);
      resetPackageEditor();
    });
  }

  async function proposeDeprecation(skillId: string) {
    const detail = await governanceApi.analysisSkill(skillId);
    const { instructions: body, path: _path, ...metadata } = detail;
    await governanceApi.proposeAnalysisSkill({ ...metadata, status: "deprecated" }, body);
  }

  return (
    <section className="admin-page" aria-label="Skills administration">
      <div className="governance-heading">
        <div><span className="eyebrow">Governed assets</span><h2>Skills</h2><p>Create and revise repeatable methods as strict, versioned packages. Installed packages change only after validation and exact approval, then reload without restarting the Agent.</p></div>
        <span className="format-chip">SKILL.md + metadata.yaml</span>
      </div>
      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      {editingSkillId ? <article className="governance-panel skill-package-editor">
        <div className="panel-heading"><div><h3>{editingSkillId === "new" ? "Add analysis Skill" : `Edit ${editingSkillId}`}</h3><p>Saving creates a proposal. The active package remains unchanged until approval and complete registry validation.</p></div><button type="button" onClick={resetPackageEditor}>Cancel edit</button></div>
        <label>metadata.yaml (JSON editor; saved as YAML)<textarea aria-label="Skill metadata" rows={18} value={metadataText} onChange={(event) => setMetadataText(event.target.value)} /></label>
        <label>SKILL.md<textarea aria-label="Skill instructions" rows={16} value={instructions} onChange={(event) => setInstructions(event.target.value)} /></label>
        <div className="approval-actions"><button className="approve" type="button" disabled={busy || instructions.trim().length < 20} onClick={() => void submitPackage()}>Create version proposal</button></div>
      </article> : null}

      <article className="governance-panel installed-skill-panel">
        <div className="panel-heading">
          <div><h3>Installed analysis skills</h3><p>These packages are available to the deterministic analysis planner. Edit creates a patch version; Delete creates a deprecation proposal and preserves recoverable history.</p></div>
          <div className="panel-actions"><span className="format-chip">{installedSkills.length} packages</span><button type="button" onClick={startNewSkill}>Add analysis Skill</button></div>
        </div>
        <div className="installed-skill-list">
          {installedSkills.length === 0 ? <p>No installed analysis skills.</p> : installedSkills.map((skill) => (
            <details className="installed-skill" key={`${skill.id}@${skill.version}`}>
              <summary><span>{skill.name}</span><small>v{skill.version} · {skill.status}</small></summary>
              <p>{skill.description}</p>
              <dl className="skill-metadata-grid">
                <div><dt>Registry ID</dt><dd><code>{skill.id}</code></dd></div><div><dt>Owner</dt><dd>{skill.owner}</dd></div><div><dt>Risk</dt><dd>{skill.risk_level}</dd></div><div><dt>Approval</dt><dd>{skill.approval.required ? "Required" : "Not required"}</dd></div><div><dt>Analysis intents</dt><dd>{skill.analysis_intents.join(", ")}</dd></div><div><dt>Prerequisites</dt><dd>{skill.prerequisite_skills.join(", ") || "None"}</dd></div><div><dt>Required metadata</dt><dd>{skill.required_metadata.join(", ") || "None"}</dd></div><div><dt>Tools</dt><dd>{skill.required_tools.join(", ") || "Controlled library only"}</dd></div>
              </dl>
              {skill.deterministic_operations.length > 0 ? <div className="skill-operations"><strong>Deterministic operations</strong><span>{skill.deterministic_operations.join(", ")}</span></div> : null}
              <div className="approval-actions"><button type="button" disabled={busy} onClick={() => void startEditSkill(skill.id)}>Edit</button>{skill.status === "active" ? <ConfirmAction label="Delete / deactivate" message={`Create a reviewed deprecation proposal for ${skill.name}?`} disabled={busy} onConfirm={() => void act(() => proposeDeprecation(skill.id))} /> : null}</div>
            </details>
          ))}
        </div>
      </article>

      <article className="governance-panel skill-standard">
        <h3>Package contract</h3>
        <div className="package-tree"><code>skill-name/</code><code>├─ SKILL.md</code><code>├─ metadata.yaml</code><code>├─ examples/</code><code>└─ tests/</code></div>
        <p><strong>SKILL.md</strong> contains operating instructions. Metadata controls triggers, inputs, outputs, prerequisites, tools, risk, dates, and lifecycle. Invalid or reference-breaking packages cannot be approved.</p>
      </article>

      <article className="governance-panel skill-list-panel">
        <div className="panel-heading"><div><h3>Skill change proposals</h3><p>Includes natural-language taught Skills and exact edits to installed analysis Skills.</p></div><span className="format-chip">{proposals.filter((item) => item.status === "pending_approval").length} waiting</span></div>
        <textarea value={teaching} onChange={(event) => setTeaching(event.target.value)} placeholder="Describe a repeatable future analysis method…" rows={4} />
        <div className="approval-actions"><button type="button" disabled={!teaching.trim() || busy} onClick={() => void act(async () => { if (revisionProposal) await governanceApi.reviseSkill(revisionProposal, teaching); else await governanceApi.proposeSkill(teaching); setTeaching(""); setRevisionProposal(null); })}>{revisionProposal ? "Create revision proposal" : "Create taught Skill proposal"}</button>{revisionProposal ? <button type="button" onClick={() => { setRevisionProposal(null); setTeaching(""); }}>Cancel revision</button> : null}</div>
        <div className="skill-list">
          {proposals.length === 0 ? <p>No Skill proposals yet.</p> : proposals.map((proposal) => (
            <details className="proposal" key={proposal.id} open={proposal.status === "pending_approval"}>
              <summary>{proposal.name} v{proposal.version} · {proposal.proposal_type.replace("_", " ")} · {proposal.status}</summary>
              <div className="proposal-meta"><span>Tools: {proposal.tool_allowlist.join(", ") || "none"}</span><span>Exact package: {proposal.payload_hash.slice(0, 20)}…</span></div>
              {Object.keys(proposal.diff).length ? <div className="package-files">{Object.entries(proposal.diff).map(([path, content]) => <details key={path} open={path === "SKILL.md"}><summary><code>{path}</code></summary><pre>{renderFile(content)}</pre></details>)}</div> : <p>Proposal content was deleted; the audit envelope remains.</p>}
              <div className="approval-actions">
                {proposal.status === "pending_approval" ? <><button className="approve" type="button" onClick={() => void act(() => governanceApi.decideSkill(proposal, "approved"))}>Approve exact package</button><button className="reject" type="button" onClick={() => void act(() => governanceApi.decideSkill(proposal, "rejected"))}>Reject</button></> : null}
                {proposal.proposal_type === "taught_skill" && proposal.status === "active" ? <><button type="button" onClick={() => { setRevisionProposal(proposal); setTeaching(String(proposal.diff["SKILL.md"] ?? "")); }}>Edit instructions</button><ConfirmAction label="Delete / deactivate" message={`Deactivate ${proposal.name} v${proposal.version}?`} disabled={busy} onConfirm={() => void act(() => governanceApi.skillLifecycle(proposal, "deprecate"))} /></> : null}
                {proposal.proposal_type === "taught_skill" && proposal.status === "deprecated" ? <button type="button" onClick={() => void act(() => governanceApi.skillLifecycle(proposal, "rollback"))}>Rollback to version</button> : null}
                {["pending_approval", "rejected"].includes(proposal.status) ? <ConfirmAction label="Delete proposal" message="Delete the proposal content while retaining its audit envelope?" disabled={busy} onConfirm={() => void act(() => governanceApi.deleteSkillProposal(proposal.id))} /> : null}
              </div>
            </details>
          ))}
        </div>
      </article>
    </section>
  );
}