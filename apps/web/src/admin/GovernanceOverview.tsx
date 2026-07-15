const assetTypes = [
  {
    href: "/admin/knowledge",
    label: "Knowledge",
    title: "Source-grounded business knowledge",
    description:
      "Versioned source documents with owner, effective date, parsing status, citations, and surfaced conflicts.",
    format: "PDF / DOCX / XLSX / CSV / TXT / Markdown",
  },
  {
    href: "/admin/skills",
    label: "Skills",
    title: "Reusable ways of working",
    description:
      "Git-tracked capability packages that turn a taught method into reviewable instructions, metadata, examples, and tests.",
    format: "SKILL.md + metadata.yaml + examples/ + tests/",
  },
  {
    href: "/admin/memory",
    label: "Memory",
    title: "Approved durable context",
    description:
      "Small structured records for explicit preferences and context, with source, scope, version, expiry, and deletion.",
    format: "scope + key + JSON value + provenance",
  },
];

export function GovernanceOverview() {
  return (
    <section className="admin-page" aria-label="Governed asset overview">
      <div className="governance-heading">
        <div>
          <span className="eyebrow">Accumulation model</span>
          <h2>Build the Agent's governed capability over time</h2>
          <p>
            The Agent can propose new assets from conversation. Administration reviews the source or
            exact diff before anything becomes active.
          </p>
        </div>
        <span className="policy-chip">Human approval gates activation</span>
      </div>

      <div className="asset-card-grid">
        {assetTypes.map((asset) => (
          <a className="asset-card" href={asset.href} key={asset.href}>
            <span className="asset-label">{asset.label}</span>
            <h3>{asset.title}</h3>
            <p>{asset.description}</p>
            <code>{asset.format}</code>
            <span className="card-link">Open {asset.label} →</span>
          </a>
        ))}
      </div>

      <article className="lifecycle-panel">
        <h3>Controlled learning loop</h3>
        <ol className="lifecycle-steps">
          <li><strong>1</strong><span>Agent proposes</span></li>
          <li><strong>2</strong><span>Admin reviews source or diff</span></li>
          <li><strong>3</strong><span>Exact payload is approved</span></li>
          <li><strong>4</strong><span>Active asset informs later runs</span></li>
          <li><strong>5</strong><span>Invocation and lifecycle are audited</span></li>
        </ol>
      </article>
    </section>
  );
}
