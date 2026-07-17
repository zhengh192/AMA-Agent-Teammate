export interface DocumentView {
  id: string;
  filename: string;
  status: string;
  version: number;
  scan_status: string;
  parser_status: string;
  chunks: number;
  content_hash: string;
  preview: string;
  source_metadata: Record<string, unknown>;
}

export interface Citation {
  chunk_id: string;
  filename: string;
  version: number;
  location: {
    page?: number;
    sheet?: string;
    section?: string;
    row_start?: number;
    row_end?: number;
    line_start?: number;
    line_end?: number;
  };
  excerpt: string;
  score: number;
}

export interface AnalysisSkillView {
  id: string;
  name: string;
  version: string;
  status: "draft" | "active" | "deprecated";
  description: string;
  owner: string;
  analysis_intents: string[];
  required_metadata: string[];
  prerequisite_skills: string[];
  required_tools: string[];
  deterministic_operations: string[];
  risk_level: "low" | "medium" | "high";
  approval: {
    required: boolean;
    reason?: string | null;
  };
  path: string;
}

export interface LearnedMetricView {
  id: string;
  metric_key: string;
  display_name: string;
  aliases: string[];
  version: number;
  status: "active" | "superseded" | "deleted";
  source: string;
  created_at: string | null;
  definition: {
    source_id: string;
    table: string;
    aggregation: string;
    value_field: string;
    time_field: string;
    filters: Array<{ field: string; operator: string; value: unknown }>;
    numerator_filters: Array<{ field: string; operator: string; value: unknown }>;
    denominator_filters: Array<{ field: string; operator: string; value: unknown }>;
    dimensions: string[];
    caveats: string[];
  };
}
export interface KnowledgeAnswer {
  answer: string;
  epistemic_label: "Confirmed" | "Unknown" | "Need confirmation";
  citations: Citation[];
  conflicts: Array<{ id: string; kind: string; name: string; status: string }>;
}

export interface SkillProposal {
  id: string;
  name: string;
  version: string;
  status: string;
  payload_hash: string;
  tool_allowlist: string[];
  diff: Record<string, unknown>;
}

export interface MemoryProposal {
  id: string;
  scope: string;
  key: string;
  value: Record<string, unknown>;
  source: string;
  payload_hash: string;
  status: string;
}

export interface MemoryView {
  id: string;
  scope: string;
  key: string;
  version: number;
  value: Record<string, unknown>;
  source: string;
  status: string;
}

async function json<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as T & { error?: { message?: string } };
  if (!response.ok) throw new Error(payload.error?.message ?? `Request failed (${response.status})`);
  return payload;
}

export const governanceApi = {
  async documents(): Promise<DocumentView[]> {
    return json(await fetch("/api/documents"));
  },
  async upload(file: File): Promise<DocumentView> {
    const body = new FormData();
    body.append("file", file);
    body.append("classification", "internal");
    return json(await fetch("/api/documents/upload", { method: "POST", body }));
  },
  async decideDocument(document: DocumentView, decision: "approved" | "rejected") {
    return json(await fetch(`/api/documents/${document.id}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, payload_hash: document.content_hash }),
    }));
  },
  async ask(question: string): Promise<KnowledgeAnswer> {
    return json(await fetch("/api/knowledge/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }));
  },
  async conflicts(): Promise<Array<{ id: string; kind: string; name: string; status: string }>> {
    return json(await fetch("/api/knowledge/conflicts"));
  },
  async learnedMetrics(query?: string): Promise<LearnedMetricView[]> {
    const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
    return json(await fetch(`/api/learned-metrics${suffix}`));
  },  async analysisSkills(): Promise<AnalysisSkillView[]> {
    return json(await fetch("/api/analysis-skills"));
  },
  async skillProposals(): Promise<SkillProposal[]> {
    return json(await fetch("/api/skills/proposals"));
  },
  async proposeSkill(teaching: string): Promise<SkillProposal> {
    return json(await fetch("/api/skills/proposals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ teaching }),
    }));
  },
  async decideSkill(proposal: SkillProposal, decision: "approved" | "rejected") {
    return json<SkillProposal>(await fetch(`/api/skills/proposals/${proposal.id}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, payload_hash: proposal.payload_hash }),
    }));
  },
  async skillLifecycle(proposal: SkillProposal, action: "deprecate" | "rollback") {
    return json(await fetch(`/api/skills/${proposal.name}/${proposal.version}/${action}`, { method: "POST" }));
  },
  async memoryProposals(): Promise<MemoryProposal[]> {
    return json(await fetch("/api/memories/proposals"));
  },
  async memories(): Promise<MemoryView[]> {
    return json(await fetch("/api/memories"));
  },
  async proposeMemory(key: string, value: string): Promise<MemoryProposal> {
    return json(await fetch("/api/memories/proposals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scope: "project",
        key,
        value: { text: value },
        source: "explicit UI proposal",
      }),
    }));
  },
  async decideMemory(proposal: MemoryProposal, decision: "approved" | "rejected") {
    return json<MemoryProposal>(await fetch(`/api/memories/proposals/${proposal.id}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, payload_hash: proposal.payload_hash }),
    }));
  },
  async deleteMemory(id: string) {
    return json(await fetch(`/api/memories/${id}`, { method: "DELETE" }));
  },
};
