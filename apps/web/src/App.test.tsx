import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./PhaseTwoApp";

const session = {
  id: "session-1",
  title: "Test session",
  created_at: "2026-07-15T00:00:00Z",
  updated_at: "2026-07-15T00:00:00Z",
};

describe("Agent workspace", () => {
  afterEach(() => vi.unstubAllGlobals());

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
    expect(screen.getByRole("button", { name: "+ New session" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Knowledge, Skill, and Memory" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ File" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open administration" })).toHaveAttribute("href", "/admin");
  });
});