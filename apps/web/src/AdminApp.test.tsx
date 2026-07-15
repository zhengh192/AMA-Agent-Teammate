import { cleanup, render, screen } from "@testing-library/react";
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
    expect(await screen.findByText("No Knowledge sources yet.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Skill registry" })).not.toBeInTheDocument();
  });

  it("renders file-based Skills as a dedicated page", async () => {
    mockEmptyApi();
    window.history.pushState({}, "", "/admin/skills");
    render(<AdminApp />);

    expect(screen.getByRole("heading", { name: "Skills" })).toBeInTheDocument();
    expect(screen.getByText("SKILL.md", { exact: true })).toBeInTheDocument();
    expect(screen.getAllByText(/metadata\.yaml/).length).toBeGreaterThan(0);
    expect(await screen.findByText("No Skill packages yet.")).toBeInTheDocument();
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
