import { FormEvent, Fragment, useEffect, useMemo, useRef, useState } from "react";
import { getAnalysisResult, streamApproval } from "./analysisApi";
import type { AnalysisResult, ApprovalPayload } from "./analysisTypes";
import { api, streamChat } from "./api";
import { AnalysisResultTimeline } from "./AnalysisResultTimeline";
import type { ChatMessage, ChatSession, RunStatus, ServerEvent, TraceEvent } from "./types";
import "./analysis.css";
import "./chat-feedback.css";

const statusLabels: Record<RunStatus, string> = {
  clarifying: "等你补充",
  planning: "我在整理",
  waiting_approval: "等你确认",
  executing: "正在执行",
  completed: "可以继续聊",
  failed: "这次没完成",
};

const epistemicLabels: Record<string, string> = {
  Confirmed: "有依据",
  Inferred: "这是推断",
  Unknown: "目前还不知道",
  "Need confirmation": "想跟你确认一下",
};

function textValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

type StreamBuffer = { text: string; runId: string | null; completed?: boolean };

export default function PhaseTwoApp() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<RunStatus>("completed");
  const [streamText, setStreamText] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [clarification, setClarification] = useState("");
  const [clarificationRunId, setClarificationRunId] = useState<string | null>(null);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [taskPlan, setTaskPlan] = useState<string[]>([]);
  const [approval, setApproval] = useState<ApprovalPayload | null>(null);
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [revisionComment, setRevisionComment] = useState("");
  const [analysisResults, setAnalysisResults] = useState<Record<string, AnalysisResult>>({});
  const [error, setError] = useState<string | null>(null);
  const [isInitializing, setIsInitializing] = useState(true);
  const [isSessionLoading, setIsSessionLoading] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const conversationEndRef = useRef<HTMLDivElement>(null);
  const activeSessionRef = useRef<string | null>(null);
  const initializationStartedRef = useRef(false);

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? null,
    [sessions, activeSessionId],
  );
  const lastMessageIndexByRun = useMemo(() => {
    const indexes = new Map<string, number>();
    messages.forEach((message, index) => {
      if (message.run_id) indexes.set(message.run_id, index);
    });
    return indexes;
  }, [messages]);
  const persistedClarification = useMemo(
    () => messages.some((message) => (
      message.run_id === clarificationRunId
      && message.role === "assistant"
      && message.epistemic_label === "Need confirmation"
      && message.content === clarification
    )),
    [messages, clarification, clarificationRunId],
  );


  useEffect(() => {
    conversationEndRef.current?.scrollIntoView?.({
      behavior: streamText ? "auto" : "smooth",
      block: "end",
    });
  }, [messages, streamText, isThinking, clarification, analysisResults]);

  async function loadMessages(sessionId: string) {
    const loaded = await api.listMessages(sessionId);
    if (activeSessionRef.current !== sessionId) return;

    const runIds = [...new Set(loaded.flatMap((item) => item.run_id ? [item.run_id] : []))];
    const resultEntries = await Promise.all(
      runIds.map(async (runId) => [runId, await getAnalysisResult(runId).catch(() => null)] as const),
    );
    if (activeSessionRef.current !== sessionId) return;
    setStreamText("");
    setMessages(loaded);
    const loadedResults: Record<string, AnalysisResult> = {};
    for (const [runId, result] of resultEntries) {
      if (result) loadedResults[runId] = result;
    }
    setAnalysisResults(loadedResults);

    const latestRun = [...loaded].reverse().find((item) => item.run_id)?.run_id ?? null;
    if (latestRun) setCurrentRunId(latestRun);
    const latestMessage = loaded.at(-1);
    if (
      latestMessage?.role === "assistant"
      && latestMessage.epistemic_label === "Need confirmation"
      && latestMessage.run_id
    ) {
      setClarification(latestMessage.content);
      setClarificationRunId(latestMessage.run_id);
      setStatus("clarifying");
    }
  }
  async function selectSession(sessionId: string) {
    setIsSessionLoading(true);
    activeSessionRef.current = sessionId;
    setActiveSessionId(sessionId);
    setClarificationRunId(null);
    setClarification("");
    setApproval(null);
    setRevisionOpen(false);
    setRevisionComment("");
    setAnalysisResults({});
    setStreamText("");
    setIsThinking(false);
    setTrace([]);
    setTaskPlan([]);
    try {
      await loadMessages(sessionId);
    } finally {
      if (activeSessionRef.current === sessionId) setIsSessionLoading(false);
    }
  }

  async function createSession() {
    setIsSessionLoading(true);
    try {
      const session = await api.createSession("New chat");
      setSessions((current) => [session, ...current]);
      await selectSession(session.id);
    } catch (caught) {
      setIsSessionLoading(false);
      throw caught;
    }
  }

  async function deleteSession(session: ChatSession) {
    if (isSessionLoading || deletingSessionId) return;
    const confirmed = window.confirm(
      `\u5220\u9664\u4f1a\u8bdd\u201c${session.title}\u201d\uff1f\u5220\u9664\u540e\u5c06\u4ece\u5217\u8868\u4e2d\u79fb\u9664\u3002`,
    );
    if (!confirmed) return;

    setDeletingSessionId(session.id);
    setError(null);
    try {
      await api.deleteSession(session.id);
      const remaining = sessions.filter((item) => item.id !== session.id);
      setSessions(remaining);
      if (activeSessionId === session.id) {
        activeSessionRef.current = null;
        setActiveSessionId(null);
        setMessages([]);
        setAnalysisResults({});
        setTrace([]);
        setTaskPlan([]);
        setApproval(null);
        setClarification("");
        setClarificationRunId(null);
        if (remaining.length > 0) await selectSession(remaining[0].id);
        else await createSession();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to delete session.");
    } finally {
      setDeletingSessionId(null);
    }
  }
  useEffect(() => {
    if (initializationStartedRef.current) return;
    initializationStartedRef.current = true;
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
      } finally {
        setIsInitializing(false);
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

  function handleServerEvent(
    event: ServerEvent,
    buffer: StreamBuffer,
  ) {
    const runId = textValue(event.data.run_id);
    if (runId) {
      buffer.runId = runId;
      setCurrentRunId(runId);
    }
    if (event.event === "run.started" || event.event === "run.resumed") setStatus("planning");
    if (event.event === "task.plan") setTaskPlan(stringList(event.data.steps));
    if (event.event === "status") setStatus((textValue(event.data.status) || "executing") as RunStatus);
    if (event.event === "message.delta") {
      setIsThinking(false);
      buffer.text += textValue(event.data.delta);
      setStreamText(buffer.text);
    }
    if (event.event === "clarification.required") {
      setIsThinking(false);
      setStatus("clarifying");
      setClarification(textValue(event.data.question));
      setClarificationRunId(runId);
    }
    if (event.event === "analysis.plan" || event.event === "approval.required") {
      setIsThinking(false);
      setStatus("waiting_approval");
      setApproval(event.data as unknown as ApprovalPayload);
      setRevisionOpen(false);
      setRevisionComment("");
      setClarificationRunId(null);
      setClarification("");
    }
    if (event.event === "analysis.result") {
      setIsThinking(false);
      const result = event.data as unknown as AnalysisResult;
      if (result.run_id) {
        setAnalysisResults((current) => ({ ...current, [result.run_id]: result }));
      }
    }
    if (event.event === "approval.decision") {
      setIsThinking(false);
      setApproval(null);
      setRevisionOpen(false);
      if (textValue(event.data.decision) === "changes_requested") {
        setStatus("planning");
        setError(null);
      } else {
        setStatus("failed");
        setError("这次操作已取消；需要时可以直接提出新的查询或 Jira 操作。");
      }
    }
    if (event.event === "run.completed") {
      buffer.completed = true;
      setIsThinking(false);
      setStatus("completed");
      setApproval(null);
      setClarificationRunId(null);
      setClarification("");
    }
    if (event.event === "error") {
      setIsThinking(false);
      setStatus("failed");
      setError(textValue(event.data.message) || "The run failed. Review the safe trace.");
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const content = input.trim();
    if (!content || !activeSessionId || isSessionLoading || ["executing", "planning", "waiting_approval"].includes(status)) return;
    setInput("");
    setError(null);
    setStreamText("");
    setTaskPlan([]);
    setIsThinking(true);
    if (!clarificationRunId) setClarification("");
    setStatus("planning");
    setMessages((current) => [
      ...current,
      {
        id: `local-${Date.now()}`,
        session_id: activeSessionId,
        run_id: clarificationRunId,
        role: "user",
        content,
        epistemic_label: null,
        created_at: new Date().toISOString(),
      },
    ]);
    const buffer: StreamBuffer = { text: "", runId: clarificationRunId };
    try {
      await streamChat(activeSessionId, content, clarificationRunId, (serverEvent) =>
        handleServerEvent(serverEvent, buffer),
      );
      await loadMessages(activeSessionId);
      if (buffer.completed) {
        setStatus("completed");
        setClarificationRunId(null);
        setClarification("");
      }
      if (buffer.runId) await refreshTrace(buffer.runId);
      setStreamText("");
      setIsThinking(false);
    } catch (caught) {
      setIsThinking(false);
      setStatus("failed");
      setError(caught instanceof Error ? caught.message : "Unable to send message.");
    }
  }

  async function decide(
    statusValue: "approved" | "rejected" | "changes_requested",
    comment?: string,
  ) {
    if (!approval || !activeSessionId) return;
    const requestedRevision = statusValue === "changes_requested" ? comment?.trim() : undefined;
    if (statusValue === "changes_requested" && !requestedRevision) return;
    const previousRunId = approval.run_id;
    setError(null);
    setStatus(statusValue === "changes_requested" ? "planning" : "executing");
    setStreamText("");
    setIsThinking(true);
    const buffer: StreamBuffer = { text: "", runId: previousRunId };
    try {
      await streamApproval(
        previousRunId,
        approval.approval_id,
        approval.payload_hash,
        statusValue,
        (serverEvent) => handleServerEvent(serverEvent, buffer),
        requestedRevision,
      );
      await refreshTrace(previousRunId);
      if (requestedRevision) {
        setMessages((current) => [
          ...current,
          {
            id: `local-revision-${Date.now()}`,
            session_id: activeSessionId,
            run_id: null,
            role: "user",
            content: requestedRevision,
            epistemic_label: null,
            created_at: new Date().toISOString(),
          },
        ]);
        setRevisionComment("");
        const revisionBuffer: StreamBuffer = { text: "", runId: null };
        await streamChat(activeSessionId, requestedRevision, null, (serverEvent) =>
          handleServerEvent(serverEvent, revisionBuffer),
        );
        if (revisionBuffer.runId) await refreshTrace(revisionBuffer.runId);
      }
      await loadMessages(activeSessionId);
      setStreamText("");
      setIsThinking(false);
    } catch (caught) {
      setIsThinking(false);
      setStatus("failed");
      setError(caught instanceof Error ? caught.message : "这次操作没有完成，请再试一次。");
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">A</span><div><strong>AMA Teammate</strong><small>你的数据同事</small></div></div>
        <button className="new-chat" type="button" disabled={isInitializing || isSessionLoading} onClick={() => void createSession()}>+ 新对话</button>
        <nav aria-label="Chat sessions">
          {sessions.map((session) => (
            <div
              className={session.id === activeSessionId ? "session-item active" : "session-item"}
              key={session.id}
            >
              <button
                className="session"
                type="button"
                disabled={isSessionLoading}
                onClick={() => void selectSession(session.id)}
              >
                {session.title}
              </button>
              <button
                className="session-delete"
                type="button"
                aria-label={`\u5220\u9664\u4f1a\u8bdd ${session.title}`}
                title={"\u5220\u9664\u4f1a\u8bdd"}
                disabled={deletingSessionId === session.id || isSessionLoading}
                onClick={() => void deleteSession(session)}
              >
                {"\u00d7"}
              </button>
            </div>
          ))}
        </nav>
      </aside>

      <main className="workspace phase-two-workspace">
        <header className="topbar"><div><h1>{activeSession?.title ?? "AMA Data Analysis Teammate"}</h1><p>像和数据同事聊天一样，把问题、口径和想法直接告诉我</p></div><span className={`status status-${status}`} aria-live="polite">{statusLabels[status]}</span></header>
        <div className="workspace-scroll">

        <section className="conversation" aria-label="Conversation">
          {messages.length === 0 && !clarification && !streamText ? <div className="empty-state"><h2>想看什么，直接问我</h2><p>可以先说业务问题；口径不清楚时，我会只追问真正缺的部分。</p></div> : null}
          {messages.map((message, index) => (
            <Fragment key={message.id}>
              <article className={`message ${message.role}`}>
                <div className="message-meta">
                  <strong>{message.role === "user" ? "你" : "AMA"}</strong>
                  {message.epistemic_label ? <span>{epistemicLabels[message.epistemic_label] ?? message.epistemic_label}</span> : null}
                </div>
                <p>{message.content}</p>
              </article>
              {message.run_id
                && lastMessageIndexByRun.get(message.run_id) === index
                && analysisResults[message.run_id] ? (
                  <AnalysisResultTimeline result={analysisResults[message.run_id]} />
                ) : null}
            </Fragment>
          ))}
          {clarification && !persistedClarification ? <article className="message assistant clarification"><div className="message-meta"><strong>AMA</strong><span>想跟你确认一下</span></div><p>{clarification}</p></article> : null}
          {isThinking && !streamText ? <article className="message assistant thinking" role="status" aria-live="polite"><div className="message-meta"><strong>AMA</strong><span>我在看</span></div><p className="thinking-copy">我先理解一下<span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span></p></article> : null}
          {streamText ? <article className="message assistant streaming"><div className="message-meta"><strong>AMA</strong></div><p>{streamText}<span className="cursor" /></p></article> : null}
          {error ? <div className="error-banner" role="alert"><strong>这次没有顺利完成</strong><p>{error}</p></div> : null}
          <div ref={conversationEndRef} />
        </section>

        {approval?.kind === "jira_action_approval" ? (
          <section className="analysis-card approval-card" aria-label="Jira action review">
            <div className="card-heading">
              <div>
                <span className="eyebrow">写入 Jira 前需要你批准</span>
                <h2>{approval.action.action === "create" ? "我准备新建这个 Jira" : "我准备修改这个 Jira 的状态"}</h2>
              </div>
              <span className="policy-chip">{approval.policy_version}</span>
            </div>
            <p className="approval-intro">
              下面是将要提交的精确内容。批准只对这份内容生效，任何字段变化都会要求重新审批。
            </p>
            <div className="sql-review jira-action-review">
              {approval.action.action === "create" ? (
                <>
                  <p><strong>项目：</strong>{approval.action.project_key}</p>
                  <p><strong>类型：</strong>{approval.action.issue_type}{approval.action.priority ? ` · 优先级 ${approval.action.priority}` : ""}</p>
                  <p><strong>标题：</strong>{approval.action.summary}</p>
                  <p><strong>描述：</strong>{approval.action.description || "（空）"}</p>
                </>
              ) : (
                <>
                  <p><strong>工单：</strong>{approval.action.issue_key}</p>
                  <p><strong>目标状态：</strong>{approval.action.target_status}</p>
                </>
              )}
            </div>
            <div className="approval-actions">
              <button className="approve" type="button" onClick={() => void decide("approved")}>批准并执行</button>
              <button type="button" onClick={() => setRevisionOpen(true)}>这里需要改一下</button>
              <button className="reject" type="button" onClick={() => void decide("rejected")}>取消操作</button>
            </div>
            {revisionOpen ? (
              <div className="revision-panel">
                <label htmlFor="jira-revision-comment">直接告诉我想怎么改</label>
                <textarea
                  id="jira-revision-comment"
                  aria-label="Requested changes"
                  value={revisionComment}
                  onChange={(event) => setRevisionComment(event.target.value)}
                  placeholder="例如：目标状态改成 Ready for Testing；或者把标题改成……"
                  rows={3}
                  autoFocus
                />
                <div className="revision-actions">
                  <button type="button" className="approve" disabled={!revisionComment.trim()} onClick={() => void decide("changes_requested", revisionComment)}>按这个修改</button>
                  <button type="button" onClick={() => { setRevisionOpen(false); setRevisionComment(""); }}>算了</button>
                </div>
              </div>
            ) : null}
            <details className="hash">
              <summary>查看这次审批标识</summary>
              <code>{approval.payload_hash}</code>
            </details>
          </section>
        ) : null}
        {approval?.kind === "sql_approval" ? (
          <section className="analysis-card approval-card" aria-label="SQL review">
            <div className="card-heading">
              <div>
                <span className="eyebrow">执行前跟你确认一下</span>
                <h2>我准备这样查</h2>
              </div>
              <span className="policy-chip">{approval.plan.policy_version}</span>
            </div>
            <p className="approval-intro">
              我理解你想看 <strong>{approval.plan.metric}</strong>。我会按
              {" "}{approval.plan.analysis_type.replaceAll("_", " ")} 来计算，
              结果用 {approval.plan.chart_type.replaceAll("_", " ")} 呈现。
            </p>
            {approval.plan.metadata_confidence === "working_assumption" ? (
              <div className="assumption-panel">
                <strong>这部分口径目前是推断</strong>
                <p>我根据现有项目文档先这样理解；如果不对，直接告诉我哪里要改。</p>
                <ul>{approval.plan.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
              </div>
            ) : null}
            {approval.plan.metadata_confidence === "learned_definition" ? (
              <div className="assumption-panel">
                <strong>这是我们之前确认过的口径</strong>
                <p>我已经复用了之前学到的定义，你仍然可以在执行前修改。</p>
                <ul>{approval.plan.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
              </div>
            ) : null}
            {approval.plan.queries.map((query) => (
              <div className="sql-review" key={query.id}>
                <div>
                  <strong>{query.source_id}</strong>
                  <span>{query.dialect} · 最多 {query.max_rows} 行 · {query.timeout_seconds}s</span>
                </div>
                <pre><code>{query.sql}</code></pre>
                <small>参数：{JSON.stringify(query.parameters)}</small>
              </div>
            ))}
            {approval.plan.join_plan ? (
              <details open>
                <summary>跨数据源关联方式</summary>
                <pre>{JSON.stringify(approval.plan.join_plan, null, 2)}</pre>
              </details>
            ) : null}
            <div className="approval-actions">
              <button className="approve" type="button" onClick={() => void decide("approved")}>
                就这样查
              </button>
              <button type="button" onClick={() => setRevisionOpen(true)}>
                这里需要改一下
              </button>
              <button className="reject" type="button" onClick={() => void decide("rejected")}>
                先不查了
              </button>
            </div>
            {revisionOpen ? (
              <div className="revision-panel">
                <label htmlFor="revision-comment">直接告诉我想怎么改</label>
                <textarea
                  id="revision-comment"
                  aria-label="Requested changes"
                  value={revisionComment}
                  onChange={(event) => setRevisionComment(event.target.value)}
                  placeholder="例如：改成 case creation rate，按天看，沿用刚才确认的分子和分母。"
                  rows={3}
                  autoFocus
                />
                <div className="revision-actions">
                  <button
                    type="button"
                    className="approve"
                    disabled={!revisionComment.trim()}
                    onClick={() => void decide("changes_requested", revisionComment)}
                  >
                    按这个修改
                  </button>
                  <button type="button" onClick={() => {
                    setRevisionOpen(false);
                    setRevisionComment("");
                  }}>
                    算了
                  </button>
                </div>
              </div>
            ) : null}
            <details className="hash">
              <summary>查看这次审批标识</summary>
              <code>{approval.payload_hash}</code>
            </details>
          </section>
        ) : null}


        </div>
        <section className="inspection">
          <details>
            <summary>看看我这次准备怎么做</summary>
            <p>任务编号：{currentRunId ?? "还没开始"}</p>
            {taskPlan.length ? (
              <ol className="task-plan">
                {taskPlan.map((step) => <li key={step}>{step}</li>)}
              </ol>
            ) : <p>现在没有进行中的步骤。</p>}
          </details>
          <details>
            <summary>查看审计记录（{trace.length}）</summary>
            {trace.length === 0 ? <p>还没有审计记录。</p> : (
              <ul className="trace-list">
                {trace.map((item) => <li key={item.id}><code>{item.event_type}</code> · {item.status}</li>)}
              </ul>
            )}
          </details>
        </section>

        <form className="composer agent-composer" onSubmit={(event) => void sendMessage(event)}><textarea aria-label="Message" disabled={isSessionLoading} value={input} onChange={(event) => setInput(event.target.value)} placeholder={clarificationRunId ? "把你知道的部分告诉我就行…" : approval ? "先确认上面的精确操作，或直接说想改哪里…" : "直接说你想了解什么…"} rows={2} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} /><button className="send" type="submit" disabled={isSessionLoading || !input.trim() || ["executing", "planning", "waiting_approval"].includes(status)}>发送</button></form>
        <footer>知识、技能和长期记忆在后台维护。 <a href="/admin">打开后台</a></footer>
      </main>
    </div>
  );
}
