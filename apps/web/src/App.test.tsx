import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./PhaseTwoApp";

vi.mock("./PlotlyFigure", () => ({
  PlotlyFigure: () => <div aria-label="Analysis chart" />,
}));

const session = {
  id: "session-1",
  title: "Test session",
  created_at: "2026-07-15T00:00:00Z",
  updated_at: "2026-07-15T00:00:00Z",
};

describe("Agent workspace", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders only the conversational Agent surface", async () => {
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/sessions")) {
        return new Response(JSON.stringify([session]), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Test session" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "+ 新对话" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Knowledge, Skill, and Memory" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ File" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开后台" })).toHaveAttribute("href", "/admin");
  });

  it("deletes a session and selects the next conversation", async () => {
    const secondSession = {
      ...session,
      id: "session-2",
      title: "Other session",
    };
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url.endsWith(`/api/sessions/${session.id}`) && init?.method === "DELETE") {
        return new Response(null, { status: 204 });
      }
      if (url.endsWith("/api/sessions")) {
        return new Response(JSON.stringify([session, secondSession]), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);
    await screen.findByRole("heading", { name: "Test session" });

    fireEvent.click(screen.getByRole("button", { name: "\u5220\u9664\u4f1a\u8bdd Test session" }));

    expect(await screen.findByRole("heading", { name: "Other session" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Test session" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/sessions/${session.id}`,
      { method: "DELETE" },
    );
  });
  it("shows the user message immediately, then a natural thinking state, then streamed text", async () => {
    const encoder = new TextEncoder();
    let streamController: ReadableStreamDefaultController<Uint8Array> | null = null;
    let completed = false;
    const finalMessages = [
      {
        id: "user-1",
        session_id: session.id,
        run_id: "run-1",
        role: "user",
        content: "Show this immediately",
        epistemic_label: null,
        created_at: "2026-07-15T00:00:01Z",
      },
      {
        id: "assistant-1",
        session_id: session.id,
        run_id: "run-1",
        role: "assistant",
        content: "Streamed answer",
        epistemic_label: "Confirmed",
        created_at: "2026-07-15T00:00:02Z",
      },
    ];

    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/sessions")) {
        return new Response(JSON.stringify([session]), { status: 200 });
      }
      if (url.endsWith(`/api/sessions/${session.id}/messages/stream`)) {
        return new Response(new ReadableStream<Uint8Array>({
          start(controller) {
            streamController = controller;
            controller.enqueue(encoder.encode(
              'event: run.started\ndata: {"run_id":"run-1","status":"planning"}\n\n',
            ));
          },
        }), { status: 200, headers: { "Content-Type": "text/event-stream" } });
      }
      if (url.endsWith(`/api/sessions/${session.id}/messages`)) {
        return new Response(JSON.stringify(completed ? finalMessages : []), { status: 200 });
      }
      if (url.endsWith("/api/runs/run-1/analysis")) {
        return new Response(JSON.stringify({}), { status: 404 });
      }
      if (url.endsWith("/api/runs/run-1/trace")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await screen.findByRole("heading", { name: "Test session" });

    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), {
      target: { value: "Show this immediately" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(screen.getByText("Show this immediately")).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent("我先理解一下");

    await act(async () => {
      streamController?.enqueue(encoder.encode(
        'event: message.delta\ndata: {"run_id":"run-1","delta":"Streamed answer"}\n\n',
      ));
    });
    expect(await screen.findByText("Streamed answer")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    completed = true;
    await act(async () => {
      streamController?.enqueue(encoder.encode(
        'event: run.completed\ndata: {"run_id":"run-1","status":"completed"}\n\n',
      ));
      streamController?.enqueue(encoder.encode(
        'event: stream.end\ndata: {"run_id":"run-1"}\n\n',
      ));
      streamController?.close();
    });

    await waitFor(() => {
      expect(screen.getAllByText("Show this immediately")).toHaveLength(1);
      expect(screen.getByText("有依据")).toBeInTheDocument();
    });
  });
  it("keeps an earlier analysis result inline after a newer turn", async () => {
    const messages = [
      {
        id: "user-1",
        session_id: session.id,
        run_id: "run-1",
        role: "user",
        content: "First data question",
        epistemic_label: null,
        created_at: "2026-07-15T00:00:01Z",
      },
      {
        id: "assistant-1",
        session_id: session.id,
        run_id: "run-1",
        role: "assistant",
        content: "First analysis answer",
        epistemic_label: "Confirmed",
        created_at: "2026-07-15T00:00:02Z",
      },
      {
        id: "user-2",
        session_id: session.id,
        run_id: "run-2",
        role: "user",
        content: "Second data question",
        epistemic_label: null,
        created_at: "2026-07-15T00:00:03Z",
      },
      {
        id: "assistant-2",
        session_id: session.id,
        run_id: "run-2",
        role: "assistant",
        content: "Which date range?",
        epistemic_label: "Need confirmation",
        created_at: "2026-07-15T00:00:04Z",
      },
    ];
    const analysisResult = {
      id: "result-1",
      run_id: "run-1",
      plan_id: "plan-1",
      status: "completed",
      datasets: [{
        id: "dataset-1",
        columns: ["value"],
        rows: [{ value: 7.05 }],
        row_count: 1,
        quality: { row_count: 1, missing_by_column: { value: 0 }, duplicate_rows: 0, warnings: [] },
      }],
      join_quality: null,
      computation: {
        summary: { value: 7.05 },
        conclusions: [{ text: "The value is 7.05%.", epistemic_label: "Confirmed", evidence_ids: ["evidence-1"] }],
        evidence: [{
          id: "evidence-1",
          title: "Computed value",
          calculation: "bounded calculation",
          epistemic_label: "Confirmed",
          confidence: 1,
          limitations: [],
          support: { value: 7.05 },
        }],
      },
      chart: { chart_type: "kpi", figure: { data: [], layout: {} }, fallback_table: false },
      csv_artifact_id: "artifact-1",
    };

    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/sessions")) {
        return new Response(JSON.stringify([session]), { status: 200 });
      }
      if (url.endsWith(`/api/sessions/${session.id}/messages`)) {
        return new Response(JSON.stringify(messages), { status: 200 });
      }
      if (url.endsWith("/api/runs/run-1/analysis")) {
        return new Response(JSON.stringify(analysisResult), { status: 200 });
      }
      if (url.endsWith("/api/runs/run-2/analysis")) {
        return new Response(JSON.stringify({}), { status: 404 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const firstAnswer = await screen.findByText("First analysis answer");
    const result = await screen.findByRole("region", { name: "Analysis results" });
    const secondQuestion = screen.getByText("Second data question");
    expect(firstAnswer.compareDocumentPosition(result) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(result.compareDocumentPosition(secondQuestion) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByText("Which date range?")).toHaveLength(1);
    expect(screen.getByText("Evidence 1")).toBeInTheDocument();
    expect(screen.queryByText("evidence-1")).not.toBeInTheDocument();
  });
  it("regenerates a plan from natural revision feedback", async () => {
    let messageStreamCount = 0;
    const requestBodies: Array<Record<string, unknown>> = [];
    const planPayload = (metric: string, suffix: string) => ({
      kind: "sql_approval",
      run_id: `run-${suffix}`,
      plan_id: `plan-${suffix}`,
      approval_id: `approval-${suffix}`,
      payload_hash: "a".repeat(64),
      status: "waiting_approval",
      plan: {
        id: `plan-${suffix}`,
        goal: `Compute ${metric}`,
        analysis_type: "trend",
        metric,
        dimensions: ["period"],
        chart_type: "line",
        success_criteria: "Return the requested calculation.",
        metadata_confidence: "authoritative",
        assumptions: [],
        queries: [{
          id: `query-${suffix}`,
          source_id: "super_agent_uat",
          dialect: "mysql",
          sql: "SELECT 1 AS value LIMIT 1",
          parameters: {},
          max_rows: 200,
          max_result_bytes: 262144,
          timeout_seconds: 10,
          policy_version: "sql-readonly-v1",
        }],
        join_plan: null,
        policy_version: "sql-readonly-v1",
      },
    });
    const sse = (events: Array<[string, Record<string, unknown>]>) => new Response(
      events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(""),
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    );
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (init?.body) requestBodies.push(JSON.parse(String(init.body)) as Record<string, unknown>);
      if (url.endsWith("/api/sessions")) return new Response(JSON.stringify([session]), { status: 200 });
      if (url.endsWith(`/api/sessions/${session.id}/messages/stream`)) {
        messageStreamCount += 1;
        const payload = messageStreamCount === 1
          ? planPayload("Traffic", "old")
          : planPayload("Case Creation Rate", "revised");
        return sse([
          ["run.started", { run_id: payload.run_id, status: "planning" }],
          ["task.plan", { run_id: payload.run_id, steps: ["Resolve requested outcome", "Prepare bounded action"] }],
          ["approval.required", payload],
          ["stream.end", { run_id: payload.run_id }],
        ]);
      }
      if (url.endsWith("/api/runs/run-old/approval/stream")) {
        return sse([
          ["approval.decision", { run_id: "run-old", decision: "changes_requested" }],
          ["stream.end", { run_id: "run-old" }],
        ]);
      }
      if (url.includes("/api/runs/") && url.endsWith("/trace")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (url.includes("/api/runs/") && url.endsWith("/analysis")) {
        return new Response(JSON.stringify({}), { status: 404 });
      }
      if (url.endsWith(`/api/sessions/${session.id}/messages`)) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await screen.findByRole("heading", { name: "Test session" });
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), {
      target: { value: "Traffic daily trend" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText("Traffic")).toBeInTheDocument();
    expect(await screen.findByText("Resolve requested outcome")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "这里需要改一下" }));
    const generate = screen.getByRole("button", { name: "按这个修改" });
    expect(generate).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "Requested changes" }), {
      target: { value: "case creation rate daily trend" },
    });
    fireEvent.click(generate);

    expect(await screen.findByText("Case Creation Rate")).toBeInTheDocument();
    expect(requestBodies).toContainEqual(expect.objectContaining({
      status: "changes_requested",
      comment: "case creation rate daily trend",
    }));
    expect(requestBodies).toContainEqual({ content: "case creation rate daily trend" });
  });
  it("renders exact Jira transition approval and submits the matching hash", async () => {
    const approvalBodies: Array<Record<string, unknown>> = [];
    const payload = {
      kind: "jira_action_approval",
      run_id: "run-jira",
      action_id: "action-jira",
      approval_id: "approval-jira",
      payload_hash: "b".repeat(64),
      status: "waiting_approval",
      policy_version: "jira-actions-v1",
      action: {
        action: "transition",
        issue_key: "LAIR-1903",
        project_key: null,
        jql: null,
        max_results: 25,
        summary: null,
        description: null,
        issue_type: null,
        priority: null,
        target_status: "Done",
      },
    };
    const sse = (events: Array<[string, Record<string, unknown>]>) => new Response(
      events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(""),
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    );
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/sessions")) return new Response(JSON.stringify([session]), { status: 200 });
      if (url.endsWith(`/api/sessions/${session.id}/messages/stream`)) {
        return sse([
          ["run.started", { run_id: "run-jira", status: "planning" }],
          ["approval.required", payload],
          ["stream.end", { run_id: "run-jira" }],
        ]);
      }
      if (url.endsWith("/api/runs/run-jira/approval/stream")) {
        if (init?.body) approvalBodies.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return sse([
          ["message.delta", { run_id: "run-jira", delta: "已把 LAIR-1903 更新到 Done。" }],
          ["run.completed", { run_id: "run-jira", status: "completed" }],
          ["stream.end", { run_id: "run-jira" }],
        ]);
      }
      if (url.includes("/api/runs/") && url.endsWith("/analysis")) return new Response("{}", { status: 404 });
      return new Response(JSON.stringify([]), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await screen.findByRole("heading", { name: "Test session" });
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), {
      target: { value: "把 LAIR-1903 状态改成 Done" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByRole("region", { name: "Jira action review" })).toBeInTheDocument();
    expect(screen.getByText("LAIR-1903")).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "批准并执行" }));

    await waitFor(() => expect(approvalBodies).toContainEqual({
      approval_id: "approval-jira",
      payload_hash: "b".repeat(64),
      status: "approved",
    }));
  });
});
