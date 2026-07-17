import type { ServerEvent } from "./types";

export interface AnalysisQueryPreview {
  id: string;
  source_id: string;
  dialect: string;
  sql: string;
  parameters: Record<string, string | number | boolean | null>;
  max_rows: number;
  max_result_bytes: number;
  timeout_seconds: number;
  policy_version: string;
}

export interface AnalysisPlanView {
  id: string;
  goal: string;
  analysis_type: string;
  metric: string;
  dimensions: string[];
  chart_type: string;
  success_criteria: string;
  metadata_confidence: "authoritative" | "working_assumption" | "learned_definition";
  assumptions: string[];
  queries: AnalysisQueryPreview[];
  join_plan: Record<string, unknown> | null;
  policy_version: string;
}

export interface ApprovalPayload {
  kind: "sql_approval";
  run_id: string;
  plan_id: string;
  approval_id: string;
  payload_hash: string;
  status: "waiting_approval";
  plan: AnalysisPlanView;
}

export interface DatasetQuality {
  row_count: number;
  missing_by_column: Record<string, number>;
  duplicate_rows: number;
  warnings: string[];
}

export interface AnalysisDataset {
  id: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  row_count: number;
  quality: DatasetQuality;
}

export interface EvidenceRecord {
  id: string;
  title: string;
  calculation: string;
  epistemic_label: string;
  confidence: number;
  limitations: string[];
  support: Record<string, unknown>;
}

export interface AnalysisResult {
  id: string;
  run_id: string;
  plan_id: string;
  status: "completed";
  datasets: AnalysisDataset[];
  join_quality: Record<string, unknown> | null;
  computation: {
    summary: Record<string, unknown>;
    conclusions: Array<{
      text: string;
      epistemic_label: string;
      evidence_ids: string[];
    }>;
    evidence: EvidenceRecord[];
  };
  chart: {
    chart_type: string;
    figure: { data: unknown[]; layout: Record<string, unknown> };
    fallback_table: boolean;
  };
  csv_artifact_id: string;
}

export type AnalysisEventHandler = (event: ServerEvent) => void;
