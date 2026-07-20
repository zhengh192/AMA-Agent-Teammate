import type { ChatMessage, ChatSession, ServerEvent, TraceEvent } from "./types";

async function jsonRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      error?: { message?: string };
    };
    throw new Error(payload.error?.message ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export const api = {
  listSessions: () => jsonRequest<ChatSession[]>("/api/sessions"),
  createSession: (title: string) =>
    jsonRequest<ChatSession>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  deleteSession: async (sessionId: string) => {
    const response = await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
    if (!response.ok) throw new Error(`Unable to delete session (${response.status})`);
  },  listMessages: (sessionId: string) =>
    jsonRequest<ChatMessage[]>(`/api/sessions/${sessionId}/messages`),
  getTrace: (runId: string) => jsonRequest<TraceEvent[]>(`/api/runs/${runId}/trace`),
};

function parseEvent(block: string): ServerEvent | null {
  let event = "message";
  let data = "{}";
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7);
    if (line.startsWith("data: ")) data = line.slice(6);
  }
  try {
    return { event, data: JSON.parse(data) as Record<string, unknown> };
  } catch {
    return null;
  }
}

export async function streamChat(
  sessionId: string,
  content: string,
  runId: string | null,
  onEvent: (event: ServerEvent) => void,
): Promise<void> {
  const url = runId
    ? `/api/runs/${runId}/resume/stream`
    : `/api/sessions/${sessionId}/messages/stream`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`Streaming request failed (${response.status})`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replaceAll("\r\n", "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = parseEvent(block);
      if (event) onEvent(event);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
}
