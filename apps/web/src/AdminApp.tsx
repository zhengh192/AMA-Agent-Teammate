import { GovernanceCenter } from "./GovernanceCenter";
import "./admin.css";

export default function AdminApp() {
  return (
    <div className="admin-shell">
      <header className="admin-header">
        <div>
          <span className="eyebrow">Administration</span>
          <h1>AMA Governance Console</h1>
          <p>Review and maintain Knowledge, Skills, and Memory outside the Agent workspace.</p>
        </div>
        <a href="/">Return to Agent</a>
      </header>
      <main className="admin-main">
        <GovernanceCenter />
      </main>
    </div>
  );
}
