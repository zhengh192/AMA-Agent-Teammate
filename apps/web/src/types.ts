export type RunStatus =
  | "clarifying"
  | "planning"
  | "waiting_approval"
  | "executing"
  | "completed"
  | "failed";

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  run_id: string | null;
  role: "user" | "assistant" | "system";
  content: string;
  epistemic_label: string | null;
  created_at: string;
}

export interface TraceEvent {
  id: string;
  event_type: string;
  graph_node: string | null;
  status: string;
  safe_details: Record<string, unknown>;
  created_at: string;
}

export interface ServerEvent {
  event: string;
  data: Record<string, unknown>;
}
