import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import App from "./PhaseTwoApp";

vi.mock("./PlotlyFigure", () => ({
  PlotlyFigure: () => <div aria-label="Analysis chart" />,
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("clears a stale SQL approval when resumed execution fails", async () => {
  const session = {
    id: "session-failure",
    title: "Failure recovery",
    created_at: "2026-07-20T00:00:00Z",
    updated_at: "2026-07-20T00:00:00Z",
  };
  const approval = {
    kind: "sql_approval",
    run_id: "run-failure",
    plan_id: "plan-failure",
    approval_id: "approval-failure",
    payload_hash: "a".repeat(64),
    status: "waiting_approval",
    plan: {
      id: "plan-failure",
      goal: "Diagnose a low day",
      analysis_type: "journey_diagnostic",
      metric: "Case Journey Stage Diagnostic",
      dimensions: ["comparison_window", "exit_stage"],
      chart_type: "bar",
      success_criteria: "Return evidence.",
      metadata_confidence: "authoritative",
      assumptions: [],
      queries: [{
        id: "query-failure",
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
  };
  const sse = (events: Array<[string, Record<string, unknown>]>) => new Response(
    events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(""),
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
  const fetchMock = vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url.endsWith("/api/sessions")) return new Response(JSON.stringify([session]), { status: 200 });
    if (url.endsWith(`/api/sessions/${session.id}/messages/stream`)) return sse([
      ["run.started", { run_id: approval.run_id, status: "planning" }],
      ["approval.required", approval],
      ["stream.end", { run_id: approval.run_id }],
    ]);
    if (url.endsWith(`/api/runs/${approval.run_id}/approval/stream`)) return sse([
      ["error", { run_id: approval.run_id, message: "Evidence validation failed after query execution." }],
      ["stream.end", { run_id: approval.run_id }],
    ]);
    if (url.endsWith(`/api/sessions/${session.id}/messages`)) return new Response("[]", { status: 200 });
    if (url.endsWith(`/api/runs/${approval.run_id}/analysis`)) return new Response("{}", { status: 404 });
    return new Response("[]", { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  await screen.findByRole("heading", { name: session.title });
  const composer = screen.getByRole("textbox", { name: "Message" });
  fireEvent.change(composer, { target: { value: "Why was July 11 low?" } });
  fireEvent.submit(composer.closest("form")!);
  const review = await screen.findByRole("region", { name: "SQL review" });
  fireEvent.click(review.querySelector("button.approve")!);

  expect(await screen.findByRole("alert")).toHaveTextContent("Evidence validation failed");
  await waitFor(() => expect(screen.queryByRole("region", { name: "SQL review" })).not.toBeInTheDocument());
});
