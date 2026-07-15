import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AdminApp from "./AdminApp";

describe("Governance console", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("keeps Knowledge, Skill, and Memory maintenance in administration", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(async () =>
      new Response(JSON.stringify([]), { status: 200 })
    ));

    render(<AdminApp />);

    expect(screen.getByRole("heading", { name: "AMA Governance Console" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to Agent" })).toHaveAttribute("href", "/");
    expect(await screen.findByRole("heading", { name: "Knowledge, Skill, and Memory" })).toBeInTheDocument();
    expect(screen.getByText("Knowledge documents")).toBeInTheDocument();
    expect(screen.getByText("Skill proposals")).toBeInTheDocument();
    expect(screen.getByText("Long-term Memory")).toBeInTheDocument();
  });
});