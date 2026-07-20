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
    expect(screen.getByRole("heading", { name: "Taught skill proposals" })).toBeInTheDocument();
    expect(await screen.findByText("No installed analysis skills.")).toBeInTheDocument();
    expect(await screen.findByText("No taught skill proposals yet.")).toBeInTheDocument();
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
});
