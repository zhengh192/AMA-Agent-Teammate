import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AdminApp from "./AdminApp";

function mockEmptyApi() {
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(async () =>
    new Response(JSON.stringify([]), { status: 200 })
  ));
}

describe("Governance console", () => {
  afterEach(() => {
    cleanup();
    window.history.pushState({}, "", "/");
    vi.unstubAllGlobals();
  });

  it("presents the governed accumulation model on the overview", () => {
    window.history.pushState({}, "", "/admin");
    render(<AdminApp />);

    expect(screen.getByRole("heading", { name: "AMA Governance Console" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Build the Agent's governed capability over time" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Knowledge/ })).toHaveAttribute("href", "/admin/knowledge");
    expect(screen.getByRole("link", { name: /Open Skills/ })).toHaveAttribute("href", "/admin/skills");
    expect(screen.getByRole("link", { name: /Open Memory/ })).toHaveAttribute("href", "/admin/memory");
  });

  it("renders Knowledge as a dedicated page", async () => {
    mockEmptyApi();
    window.history.pushState({}, "", "/admin/knowledge");
    render(<AdminApp />);

    expect(screen.getByRole("heading", { name: "Knowledge" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Source library" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Active business rules" })).toBeInTheDocument();
    expect(await screen.findByText("No Knowledge sources yet.")).toBeInTheDocument();
    expect(await screen.findByText("No active business rules.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Skill registry" })).not.toBeInTheDocument();
  });

  it("renders file-based Skills as a dedicated page", async () => {
    mockEmptyApi();
    window.history.pushState({}, "", "/admin/skills");
    render(<AdminApp />);

    expect(screen.getByRole("heading", { name: "Skills" })).toBeInTheDocument();
    expect(screen.getByText("SKILL.md", { exact: true })).toBeInTheDocument();
    expect(screen.getAllByText(/metadata\.yaml/).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Installed analysis skills" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Skill change proposals" })).toBeInTheDocument();
    expect(await screen.findByText("No installed analysis skills.")).toBeInTheDocument();
    expect(await screen.findByText("No Skill proposals yet.")).toBeInTheDocument();
  });


  it("creates an edited Memory version proposal from an active record", async () => {
    const memory = {
      id: "memory-1",
      scope: "project",
      key: "project_identity",
      version: 1,
      value: { text: "Super Agent pilot" },
      source: "approved conversation",
      status: "active",
      expires_at: null,
      created_at: "2026-07-19T10:00:00Z",
      deleted_at: null,
    };
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/memories/memory-1" && init?.method === "PATCH") {
        return new Response(JSON.stringify({
          id: "proposal-2",
          scope: "project",
          key: "project_identity",
          value: { text: "Super Agent production pilot" },
          source: "explicit correction",
          payload_hash: "hash-2",
          status: "pending_approval",
          expires_at: null,
          created_at: "2026-07-19T11:00:00Z",
          decided_at: null,
        }), { status: 200 });
      }
      if (url === "/api/memories/proposals") {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (url === "/api/memories") {
        return new Response(JSON.stringify([memory]), { status: 200 });
      }
      return new Response(JSON.stringify({ error: { message: "Unexpected request" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    window.history.pushState({}, "", "/admin/memory");
    render(<AdminApp />);

    expect(await screen.findByText("project_identity v1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByRole("heading", { name: "Edit Memory" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Memory value" }), {
      target: { value: "Super Agent production pilot" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Memory source" }), {
      target: { value: "explicit correction" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save version proposal" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/memories/memory-1",
      expect.objectContaining({ method: "PATCH" }),
    ));
  });
  it("renders structured Memory as a dedicated page", async () => {
    mockEmptyApi();
    window.history.pushState({}, "", "/admin/memory");
    render(<AdminApp />);

    expect(screen.getByRole("heading", { name: "Memory" })).toBeInTheDocument();
    expect(screen.getByText("Good Memory")).toBeInTheDocument();
    expect(screen.getByText("Not Memory")).toBeInTheDocument();
    expect(await screen.findByText("No active Memory.")).toBeInTheDocument();
  });
  it("edits an installed analysis Skill through an approval proposal", async () => {
    const installed = {
      id: "metric_query",
      name: "Metric Query",
      version: "1.0.0",
      status: "active",
      description: "Resolve and calculate a governed metric definition.",
      owner: "Data team",
      reviewer: "Data Governance",
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "2026-07-01T00:00:00Z",
      effective_from: "2026-07-01",
      effective_to: null,
      aliases: [],
      trigger_examples: { en: ["Query a metric"], zh: ["查询指标"] },
      analysis_intents: ["trend"],
      required_metadata: ["metric"],
      prerequisite_skills: [],
      inputs: [{ name: "metric", type: "metric", required: true, description: "Metric" }],
      outputs: [{ name: "result", type: "analysis_result", description: "Result" }],
      required_tools: ["sql_safety_gateway"],
      deterministic_operations: ["metric_resolution"],
      risk_level: "medium",
      approval: { required: false, reason: null },
      path: "skills/metric_query",
      instructions: "# Metric Query\n\nUse approved metadata before SQL planning.",
    };
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/analysis-skills" && !init?.method) return new Response(JSON.stringify([installed]), { status: 200 });
      if (url === "/api/skills/proposals" && !init?.method) return new Response(JSON.stringify([]), { status: 200 });
      if (url === "/api/analysis-skills/metric_query") return new Response(JSON.stringify(installed), { status: 200 });
      if (url === "/api/analysis-skills/proposals" && init?.method === "POST") return new Response(JSON.stringify({ id: "proposal-1" }), { status: 200 });
      return new Response(JSON.stringify({ error: { message: "Unexpected request" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    window.history.pushState({}, "", "/admin/skills");
    render(<AdminApp />);

    expect(await screen.findByText("Metric Query")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(await screen.findByRole("heading", { name: "Edit metric_query" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Skill instructions" }), {
      target: { value: "# Metric Query\n\nUse approved metadata first, then validate the exact SQL." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create version proposal" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/analysis-skills/proposals",
      expect.objectContaining({ method: "POST" }),
    ));
  });

  it("requires explicit confirmation before forgetting Memory", async () => {
    const memory = {
      id: "memory-delete",
      scope: "project",
      key: "temporary_context",
      version: 1,
      value: { text: "temporary" },
      source: "approved conversation",
      status: "active",
      expires_at: null,
      created_at: "2026-07-20T10:00:00Z",
      deleted_at: null,
    };
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/memories/proposals") return new Response(JSON.stringify([]), { status: 200 });
      if (url === "/api/memories" && !init?.method) return new Response(JSON.stringify([memory]), { status: 200 });
      if (url === "/api/memories/memory-delete" && init?.method === "DELETE") return new Response(JSON.stringify({ ...memory, status: "deleted" }), { status: 200 });
      return new Response(JSON.stringify({ error: { message: "Unexpected request" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    window.history.pushState({}, "", "/admin/memory");
    render(<AdminApp />);

    fireEvent.click(await screen.findByRole("button", { name: "Delete / forget" }));
    expect(screen.getByText(/Permanently forget temporary_context/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/memories/memory-delete",
      expect.objectContaining({ method: "DELETE" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/memories/memory-delete",
      expect.objectContaining({ method: "DELETE" }),
    ));
  });
  it("creates a governed Knowledge proposal from the admin editor", async () => {
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/knowledge/entries" && init?.method === "POST") {
        return new Response(JSON.stringify({ id: "knowledge-proposal-1" }), { status: 200 });
      }
      if (["/api/documents", "/api/knowledge/proposals", "/api/knowledge/conflicts", "/api/learned-metrics", "/api/semantic-metadata?definition_type=business_rule&status=active"].includes(url)) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response(JSON.stringify({ error: { message: "Unexpected request" } }), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    window.history.pushState({}, "", "/admin/knowledge");
    render(<AdminApp />);

    fireEvent.change(screen.getByRole("textbox", { name: "Knowledge name" }), {
      target: { value: "Pilot operating scope" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Knowledge definition" }), {
      target: { value: "The pilot supports governed internal analysis." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create proposal" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/knowledge/entries",
      expect.objectContaining({ method: "POST" }),
    ));
  });
});
