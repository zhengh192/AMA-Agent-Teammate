import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./PhaseTwoApp";

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
    expect(screen.getByRole("button", { name: "+ New session" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Knowledge, Skill, and Memory" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ File" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open administration" })).toHaveAttribute("href", "/admin");
  });

  it("shows the user message immediately, then Thinking, then streamed text", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(screen.getByText("Show this immediately")).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent("Thinking");

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
      expect(screen.getByText("Confirmed")).toBeInTheDocument();
    });
  });
});
