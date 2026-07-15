import { GovernanceOverview } from "./admin/GovernanceOverview";
import { KnowledgeAdminPage } from "./admin/KnowledgeAdminPage";
import { MemoryAdminPage } from "./admin/MemoryAdminPage";
import { SkillsAdminPage } from "./admin/SkillsAdminPage";
import "./admin.css";
import "./admin-pages.css";
import "./governance.css";

const sections = [
  { href: "/admin", label: "Overview", match: (path: string) => path === "/admin" || path === "/admin/" },
  { href: "/admin/knowledge", label: "Knowledge", match: (path: string) => path.startsWith("/admin/knowledge") },
  { href: "/admin/skills", label: "Skills", match: (path: string) => path.startsWith("/admin/skills") },
  { href: "/admin/memory", label: "Memory", match: (path: string) => path.startsWith("/admin/memory") },
];

function currentPage(path: string) {
  if (path.startsWith("/admin/knowledge")) return <KnowledgeAdminPage />;
  if (path.startsWith("/admin/skills")) return <SkillsAdminPage />;
  if (path.startsWith("/admin/memory")) return <MemoryAdminPage />;
  return <GovernanceOverview />;
}

export default function AdminApp() {
  const path = window.location.pathname;
  return (
    <div className="admin-shell">
      <header className="admin-header">
        <div>
          <span className="eyebrow">Administration</span>
          <h1>AMA Governance Console</h1>
          <p>Grow the Agent through governed Knowledge, Skills, and Memory.</p>
        </div>
        <a href="/">Return to Agent</a>
      </header>
      <nav className="admin-nav" aria-label="Governance sections">
        {sections.map((section) => <a className={section.match(path) ? "active" : ""} aria-current={section.match(path) ? "page" : undefined} href={section.href} key={section.href}>{section.label}</a>)}
      </nav>
      <main className="admin-main">
        {currentPage(path)}
      </main>
    </div>
  );
}
