import type { AnalysisResult, AnalysisEventHandler } from "./analysisTypes";
import type { ServerEvent } from "./types";

async function streamResponse(response: Response, onEvent: AnalysisEventHandler): Promise<void> {
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
    if (done) return;
  }
}

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

export async function streamApproval(
  runId: string,
  approvalId: string,
  payloadHash: string,
  status: "approved" | "rejected" | "changes_requested",
  onEvent: AnalysisEventHandler,
): Promise<void> {
  const response = await fetch(`/api/runs/${runId}/approval/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approval_id: approvalId, payload_hash: payloadHash, status }),
  });
  await streamResponse(response, onEvent);
}

export async function getAnalysisResult(runId: string): Promise<AnalysisResult | null> {
  const response = await fetch(`/api/runs/${runId}/analysis`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Analysis result request failed (${response.status})`);
  return (await response.json()) as AnalysisResult;
}
