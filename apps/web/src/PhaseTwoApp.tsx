import { FormEvent, useEffect, useMemo, useState } from "react";
import { getAnalysisResult, streamApproval } from "./analysisApi";
import type { AnalysisResult, ApprovalPayload } from "./analysisTypes";
import { api, streamChat } from "./api";
import { PlotlyFigure } from "./PlotlyFigure";
import type { ChatMessage, ChatSession, RunStatus, ServerEvent, TraceEvent } from "./types";
import "./analysis.css";

const statusLabels: Record<RunStatus, string> = {
  clarifying: "Clarifying",
  planning: "Planning",
  waiting_approval: "Waiting approval",
  executing: "Executing",
  completed: "Completed",
  failed: "Failed",
};

function textValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export default function PhaseTwoApp() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<RunStatus>("completed");
  const [streamText, setStreamText] = useState("");
  const [clarification, setClarification] = useState("");
  const [clarificationRunId, setClarificationRunId] = useState<string | null>(null);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [approval, setApproval] = useState<ApprovalPayload | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? null,
    [sessions, activeSessionId],
  );
  const finalDataset = analysisResult?.datasets.at(-1) ?? null;

  async function loadMessages(sessionId: string) {
    const loaded = await api.listMessages(sessionId);
    setMessages(loaded);
    const latestRun = [...loaded].reverse().find((item) => item.run_id)?.run_id;
    if (latestRun) {
      const result = await getAnalysisResult(latestRun).catch(() => null);
      if (result) {
        setAnalysisResult(result);
        setCurrentRunId(latestRun);
      }
    }
  }

  async function selectSession(sessionId: string) {
    setActiveSessionId(sessionId);
    setClarificationRunId(null);
    setClarification("");
    setApproval(null);
    setAnalysisResult(null);
    setStreamText("");
    setTrace([]);
    await loadMessages(sessionId);
  }

  async function createSession() {
    const session = await api.createSession("New chat");
    setSessions((current) => [session, ...current]);
    await selectSession(session.id);
  }

  useEffect(() => {
    void (async () => {
      try {
        const loaded = await api.listSessions();
        if (loaded.length) {
          setSessions(loaded);
          await selectSession(loaded[0].id);
        } else {
          await createSession();
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Failed to load sessions.");
      }
    })();
  }, []);

  async function refreshTrace(runId: string) {
    try {
      setTrace(await api.getTrace(runId));
    } catch {
      setTrace([]);
    }
  }

  function handleServerEvent(event: ServerEvent, buffer: { text: string; runId: string | null }) {
    const runId = textValue(event.data.run_id);
    if (runId) {
      buffer.runId = runId;
      setCurrentRunId(runId);
    }
    if (event.event === "run.started" || event.event === "run.resumed") setStatus("planning");
    if (event.event === "status") setStatus((textValue(event.data.status) || "executing") as RunStatus);
    if (event.event === "message.delta") {
      buffer.text += textValue(event.data.delta);
      setStreamText(buffer.text);
    }
    if (event.event === "clarification.required") {
      setStatus("clarifying");
      setClarification(textValue(event.data.question));
      setClarificationRunId(runId);
    }
    if (event.event === "analysis.plan" || event.event === "approval.required") {
      setStatus("waiting_approval");
      setApproval(event.data as unknown as ApprovalPayload);
      setClarificationRunId(null);
      setClarification("");
    }
    if (event.event === "analysis.result") {
      setAnalysisResult(event.data as unknown as AnalysisResult);
    }
    if (event.event === "approval.decision") {
      setStatus("failed");
      setApproval(null);
      setError("The SQL plan was not approved. Submit a revised analytical request when ready.");
    }
    if (event.event === "run.completed") {
      setStatus("completed");
      setApproval(null);
      setClarificationRunId(null);
      setClarification("");
    }
    if (event.event === "error") {
      setStatus("failed");
      setError(textValue(event.data.message) || "The run failed. Review the safe trace.");
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const content = input.trim();
    if (!content || !activeSessionId || ["executing", "planning", "waiting_approval"].includes(status)) return;
    setInput("");
    setError(null);
    setStreamText("");
    setAnalysisResult(null);
    if (!clarificationRunId) setClarification("");
    setStatus("planning");
    const buffer = { text: "", runId: clarificationRunId };
    try {
      await streamChat(activeSessionId, content, clarificationRunId, (serverEvent) =>
        handleServerEvent(serverEvent, buffer),
      );
      await loadMessages(activeSessionId);
      if (buffer.runId) await refreshTrace(buffer.runId);
      setStreamText("");
    } catch (caught) {
      setStatus("failed");
      setError(caught instanceof Error ? caught.message : "Unable to send message.");
    }
  }

  async function decide(statusValue: "approved" | "rejected" | "changes_requested") {
    if (!approval || !activeSessionId) return;
    setError(null);
    setStatus("executing");
    setStreamText("");
    const buffer = { text: "", runId: approval.run_id };
    try {
      await streamApproval(
        approval.run_id,
        approval.approval_id,
        approval.payload_hash,
        statusValue,
        (serverEvent) => handleServerEvent(serverEvent, buffer),
      );
      await loadMessages(activeSessionId);
      await refreshTrace(approval.run_id);
      setStreamText("");
    } catch (caught) {
      setStatus("failed");
      setError(caught instanceof Error ? caught.message : "Approval action failed.");
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">A</span><div><strong>AMA Teammate</strong><small>Phase 3</small></div></div>
        <button className="new-chat" type="button" onClick={() => void createSession()}>+ New session</button>
        <nav aria-label="Chat sessions">
          {sessions.map((session) => <button className={session.id === activeSessionId ? "session active" : "session"} key={session.id} type="button" onClick={() => void selectSession(session.id)}>{session.title}</button>)}
        </nav>
      </aside>

      <main className="workspace phase-two-workspace">
        <header className="topbar"><div><h1>{activeSession?.title ?? "AMA Data Analysis Teammate"}</h1><p>Your conversational Agent for governed questions, analysis, and source-backed answers</p></div><span className={`status status-${status}`} aria-live="polite">{statusLabels[status]}</span></header>

        <section className="conversation" aria-label="Conversation">
          {messages.length === 0 && !clarification && !streamText ? <div className="empty-state"><h2>Ask a data question</h2><p>Try: “Query revenue trend for 2025 from the PostgreSQL sales data source.”</p></div> : null}
          {messages.map((message) => <article className={`message ${message.role}`} key={message.id}><div className="message-meta"><strong>{message.role === "user" ? "You" : "AMA"}</strong>{message.epistemic_label ? <span>{message.epistemic_label}</span> : null}</div><p>{message.content}</p></article>)}
          {clarification ? <article className="message assistant clarification"><div className="message-meta"><strong>AMA</strong><span>Need confirmation</span></div><p>{clarification}</p></article> : null}
          {streamText ? <article className="message assistant streaming"><div className="message-meta"><strong>AMA</strong><span>Streaming</span></div><p>{streamText}<span className="cursor" /></p></article> : null}
          {error ? <div className="error-banner" role="alert"><strong>Safe error</strong><p>{error}</p></div> : null}
        </section>

        {approval ? <section className="analysis-card approval-card" aria-label="SQL review"><div className="card-heading"><div><span className="eyebrow">Approval required</span><h2>Analysis plan and SQL review</h2></div><span className="policy-chip">{approval.plan.policy_version}</span></div><p>{approval.plan.goal}</p><dl className="plan-grid"><div><dt>Method</dt><dd>{approval.plan.analysis_type}</dd></div><div><dt>Metric</dt><dd>{approval.plan.metric}</dd></div><div><dt>Chart</dt><dd>{approval.plan.chart_type}</dd></div><div><dt>Success</dt><dd>{approval.plan.success_criteria}</dd></div></dl>{approval.plan.queries.map((query) => <div className="sql-review" key={query.id}><div><strong>{query.source_id}</strong><span>{query.dialect} · max {query.max_rows} rows · {query.timeout_seconds}s</span></div><pre><code>{query.sql}</code></pre><small>Parameters: {JSON.stringify(query.parameters)}</small></div>)}{approval.plan.join_plan ? <details open><summary>Validated cross-source join</summary><pre>{JSON.stringify(approval.plan.join_plan, null, 2)}</pre></details> : null}<div className="approval-actions"><button className="approve" type="button" onClick={() => void decide("approved")}>Approve and execute</button><button type="button" onClick={() => void decide("changes_requested")}>Request changes</button><button className="reject" type="button" onClick={() => void decide("rejected")}>Reject</button></div><small className="hash">Exact payload: {approval.payload_hash.slice(0, 16)}…</small></section> : null}

        {analysisResult && finalDataset ? <section className="analysis-results" aria-label="Analysis results"><div className="result-toolbar"><div><span className="eyebrow">Completed</span><h2>Bounded analysis result</h2></div><a className="download" href={`/api/artifacts/${analysisResult.csv_artifact_id}/download`}>Download CSV</a></div><div className="result-grid"><article className="analysis-card chart-card"><h3>{analysisResult.chart.chart_type.replaceAll("_", " ")}</h3><PlotlyFigure figure={analysisResult.chart.figure} />{analysisResult.chart.fallback_table ? <p className="warning">The requested chart was unsuitable; a table fallback was used.</p> : null}</article><article className="analysis-card evidence-card"><h3>Evidence-linked conclusions</h3>{analysisResult.computation.conclusions.map((item) => <div className="conclusion" key={item.text}><span className={`label label-${item.epistemic_label.toLowerCase().replace(" ", "-")}`}>{item.epistemic_label}</span><p>{item.text}</p><small>Evidence: {item.evidence_ids.join(", ")}</small></div>)}</article></div><article className="analysis-card"><div className="card-heading"><h3>Result table</h3><span>{finalDataset.row_count} rows</span></div><div className="table-scroll"><table><thead><tr>{finalDataset.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{finalDataset.rows.map((row, index) => <tr key={index}>{finalDataset.columns.map((column) => <td key={column}>{String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table></div>{finalDataset.quality.warnings.map((warning) => <p className="warning" key={warning}>{warning}</p>)}</article>{analysisResult.join_quality ? <article className="analysis-card"><h3>Cross-database join quality</h3><pre>{JSON.stringify(analysisResult.join_quality, null, 2)}</pre></article> : null}<article className="analysis-card"><h3>Evidence records</h3><div className="evidence-list">{analysisResult.computation.evidence.map((item) => <details key={item.id}><summary>{item.epistemic_label} · {item.title}</summary><p>{item.calculation}</p><pre>{JSON.stringify(item.support, null, 2)}</pre>{item.limitations.map((limitation) => <p className="warning" key={limitation}>{limitation}</p>)}</details>)}</div></article></section> : null}

        <section className="inspection"><details><summary>Plan / trace context</summary><p>Run: {currentRunId ?? "Not started"}</p><p>Flow: clarify → plan → SQL policy → approval → execute → evidence</p></details><details><summary>Trace ({trace.length})</summary>{trace.length === 0 ? <p>No trace events yet.</p> : <ul className="trace-list">{trace.map((item) => <li key={item.id}><code>{item.event_type}</code> · {item.status}</li>)}</ul>}</details></section>

        <form className="composer agent-composer" onSubmit={(event) => void sendMessage(event)}><textarea aria-label="Message" value={input} onChange={(event) => setInput(event.target.value)} placeholder={clarificationRunId ? "Provide the requested clarification…" : approval ? "Review and decide the SQL plan above…" : "Message AMA Teammate…"} rows={2} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} /><button className="send" type="submit" disabled={!input.trim() || ["executing", "planning", "waiting_approval"].includes(status)}>Send</button></form>
        <footer>Governed content is maintained separately. <a href="/admin">Open administration</a></footer>
      </main>
    </div>
  );
}
