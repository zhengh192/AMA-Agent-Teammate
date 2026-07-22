import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AnalysisResultTimeline } from "./AnalysisResultTimeline";
import type { AnalysisResult } from "./analysisTypes";

vi.mock("./PlotlyFigure", () => ({
  PlotlyFigure: () => <div aria-label="Analysis chart" />,
}));

const longResponse = "The troubleshooting service is currently unavailable. ".repeat(20);

const result: AnalysisResult = {
  id: "result-1",
  run_id: "run-1",
  plan_id: "plan-1",
  status: "completed",
  datasets: [
    {
      id: "dataset-1",
      columns: [
        "record_type",
        "comparison_date",
        "comparison_window",
        "outcome",
        "agent_stage",
        "value",
        "bot_response_1",
      ],
      rows: [
        {
          record_type: "distribution",
          comparison_date: "2026-07-18",
          comparison_window: "incident",
          outcome: "FAILED",
          agent_stage: "KA",
          value: 12,
          bot_response_1: null,
        },
        {
          record_type: "response_evidence",
          comparison_date: "2026-07-18",
          comparison_window: "incident",
          outcome: "FAILED",
          agent_stage: "KA",
          value: 0,
          bot_response_1: longResponse,
        },
      ],
      row_count: 2,
      quality: { row_count: 2, missing_by_column: {}, duplicate_rows: 0, warnings: [] },
    },
  ],
  join_quality: null,
  computation: {
    summary: {
      response_language: "en",
      hierarchy: [
        {
          key: "agent_stage",
          label: "Agent stage",
          parent: {},
          display_rows: [
            {
              value: "KA",
              baseline_average_daily_count: 2,
              incident_average_daily_count: 12,
              excess_failed_sessions: 10,
              failure_share_change: 0.2,
            },
          ],
        },
      ],
      response_evidence: {
        selected_path: { agent_stage: "KA" },
        incident_sample_count: 1,
        baseline_sample_count: 0,
        samples: {
          incident: [
            {
              comparison_date: "2026-07-18",
              agent_stage: "KA",
              symptom: null,
              flow_step: null,
              bot_response: longResponse,
            },
          ],
          baseline: [],
        },
      },
    },
    conclusions: [
      { text: "KA had the largest increase.", epistemic_label: "Confirmed", evidence_ids: ["e1"] },
    ],
    evidence: [
      {
        id: "e1",
        title: "Agent-stage comparison",
        calculation: "Compared incident with baseline.",
        epistemic_label: "Confirmed",
        confidence: 0.9,
        limitations: [],
        support: {},
      },
    ],
  },
  chart: { chart_type: "bar", figure: { data: [{}], layout: {} }, fallback_table: false },
  csv_artifact_id: "csv-1",
};

describe("AnalysisResultTimeline", () => {
  it("keeps bot responses out of chart dimensions and raw result columns", () => {
    render(<AnalysisResultTimeline result={result} />);

    expect(screen.getByRole("heading", { name: "Bot-response evidence at the exit location" }))
      .toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "bot_response_1" }))
      .not.toBeInTheDocument();

    const table = screen.getByRole("table", { name: "Result table" });
    expect(within(table).getByText("KA")).toBeInTheDocument();
    expect(screen.getByText(/troubleshooting service is currently unavailable/)).toBeInTheDocument();
  });
});
