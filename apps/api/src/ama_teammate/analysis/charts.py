from __future__ import annotations

from collections import defaultdict
from typing import Any

from ama_teammate.analysis.models import (
    AnalysisComputation,
    AnalysisIntent,
    ChartKind,
    ChartSpec,
    Dataset,
)


class ChartValidationError(ValueError):
    pass


class PlotlySpecValidator:
    allowed_trace_types = {"table", "indicator", "scatter", "bar", "histogram", "heatmap"}
    forbidden_keys = {"url", "src", "images", "frames", "transforms"}

    def validate(self, figure: dict[str, Any]) -> None:
        data = figure.get("data")
        layout = figure.get("layout")
        if not isinstance(data, list) or not data or len(data) > 20:
            raise ChartValidationError("Plotly data must contain 1-20 bounded traces.")
        if not isinstance(layout, dict) or not isinstance(layout.get("title"), dict):
            raise ChartValidationError("Plotly layout requires a structured title.")
        self._walk(figure)
        points = 0
        for trace in data:
            if not isinstance(trace, dict) or trace.get("type") not in self.allowed_trace_types:
                raise ChartValidationError("Plotly trace type is not allowed.")
            for key in ("x", "y", "z", "values"):
                value = trace.get(key)
                if isinstance(value, list):
                    points += len(value)
        if points > 5_000:
            raise ChartValidationError("Plotly spec exceeds the bounded point limit.")

    def _walk(self, value: Any) -> None:
        if isinstance(value, dict):
            if self.forbidden_keys & set(value):
                raise ChartValidationError("Plotly spec contains a forbidden capability.")
            for child in value.values():
                self._walk(child)
        elif isinstance(value, list):
            for child in value:
                self._walk(child)
        elif isinstance(value, str) and (
            "<script" in value.lower() or "javascript:" in value.lower()
        ):
            raise ChartValidationError("Plotly text contains unsafe active content.")


class ChartBuilder:
    def __init__(self, validator: PlotlySpecValidator) -> None:
        self.validator = validator

    def build(
        self, intent: AnalysisIntent, dataset: Dataset, computation: AnalysisComputation
    ) -> ChartSpec:
        chart_type = intent.chart_type
        figure = self._figure(chart_type, intent, dataset, computation)
        fallback = False
        try:
            self.validator.validate(figure)
        except ChartValidationError:
            chart_type = ChartKind.TABLE
            figure = self._table_figure(intent, dataset)
            self.validator.validate(figure)
            fallback = True
        return ChartSpec(
            chart_type=chart_type,
            figure=figure,
            dataset_id=dataset.id,
            evidence_ids=[item.id for item in computation.evidence],
            fallback_table=fallback,
        )

    def _figure(
        self,
        chart_type: ChartKind,
        intent: AnalysisIntent,
        dataset: Dataset,
        computation: AnalysisComputation,
    ) -> dict[str, Any]:
        if chart_type == ChartKind.TABLE:
            return self._table_figure(intent, dataset)
        if chart_type == ChartKind.KPI:
            rate = computation.summary.get("rate")
            value = rate if isinstance(rate, (int, float)) else computation.summary.get("last", 0)
            return {
                "data": [
                    {
                        "type": "indicator",
                        "mode": "number",
                        "value": value,
                        "title": {"text": intent.metric},
                    }
                ],
                "layout": self._layout(intent),
            }
        if chart_type in {ChartKind.LINE, ChartKind.BAR}:
            trace_type = "scatter" if chart_type == ChartKind.LINE else "bar"
            x_column = "channel" if "channel" in dataset.columns else "period"
            y_column = "revenue" if "revenue" in dataset.columns else "value"
            trace: dict[str, Any] = {
                "type": trace_type,
                "x": [row.get(x_column) for row in dataset.rows],
                "y": [row.get(y_column) for row in dataset.rows],
                "name": intent.metric,
            }
            if chart_type == ChartKind.LINE:
                trace["mode"] = "lines+markers"
            return {"data": [trace], "layout": self._layout(intent)}
        if chart_type == ChartKind.STACKED_BAR:
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in dataset.rows:
                grouped[str(row.get("segment", "Unknown"))].append(row)
            traces = [
                {
                    "type": "bar",
                    "name": name,
                    "x": [row.get("period") for row in rows],
                    "y": [row.get("value") for row in rows],
                }
                for name, rows in grouped.items()
            ]
            layout = self._layout(intent)
            layout["barmode"] = "stack"
            return {"data": traces, "layout": layout}
        if chart_type == ChartKind.SCATTER:
            return {
                "data": [
                    {
                        "type": "scatter",
                        "mode": "markers",
                        "x": [row.get("spend") for row in dataset.rows],
                        "y": [row.get("revenue") for row in dataset.rows],
                        "text": [row.get("channel") for row in dataset.rows],
                        "name": "Observed pairs",
                    }
                ],
                "layout": self._layout(intent),
            }
        if chart_type == ChartKind.HISTOGRAM:
            return {
                "data": [
                    {
                        "type": "histogram",
                        "x": [row.get("value") for row in dataset.rows],
                        "name": intent.metric,
                    }
                ],
                "layout": self._layout(intent),
            }
        if chart_type == ChartKind.HEATMAP:
            values = [row.get("value", row.get("revenue", 0)) for row in dataset.rows]
            return {
                "data": [
                    {
                        "type": "heatmap",
                        "z": [values],
                        "x": [
                            str(row.get("period", index)) for index, row in enumerate(dataset.rows)
                        ],
                        "y": [intent.metric],
                    }
                ],
                "layout": self._layout(intent),
            }
        return self._table_figure(intent, dataset)

    @staticmethod
    def _layout(intent: AnalysisIntent) -> dict[str, Any]:
        return {
            "title": {"text": f"{intent.metric} — {intent.analysis_type.value}"},
            "paper_bgcolor": "#ffffff",
            "plot_bgcolor": "#ffffff",
            "showlegend": True,
            "margin": {"l": 55, "r": 20, "t": 55, "b": 50},
        }

    def _table_figure(self, intent: AnalysisIntent, dataset: Dataset) -> dict[str, Any]:
        return {
            "data": [
                {
                    "type": "table",
                    "header": {"values": dataset.columns},
                    "cells": {
                        "values": [
                            [row.get(column) for row in dataset.rows] for column in dataset.columns
                        ]
                    },
                }
            ],
            "layout": self._layout(intent),
        }
