from __future__ import annotations

import math
from collections import defaultdict
from statistics import fmean, pstdev
from typing import Any

from ama_teammate.analysis.models import (
    AnalysisComputation,
    AnalysisIntent,
    AnalysisKind,
    Conclusion,
    Dataset,
    EvidenceRecord,
    JoinQuality,
)
from ama_teammate.domain.models import EpistemicLabel, new_id


class ControlledAnalysisEngine:
    version = "controlled-analysis-v1"

    def analyze(
        self, intent: AnalysisIntent, dataset: Dataset, join_quality: JoinQuality | None
    ) -> AnalysisComputation:
        quality_evidence = self._quality_evidence(dataset)
        if intent.analysis_type == AnalysisKind.JOURNEY_DIAGNOSTIC:
            summary, evidence, conclusions = self._journey_diagnostic(dataset)
        elif intent.analysis_type == AnalysisKind.DETAIL:
            summary, evidence, conclusions = self._detail(dataset, intent)
        elif intent.analysis_type == AnalysisKind.CONTRIBUTION:
            summary, evidence, conclusions = self._contribution(dataset)
        elif intent.analysis_type == AnalysisKind.SEGMENT_BREAKDOWN:
            summary, evidence, conclusions = self._segment(dataset, intent)
        elif intent.analysis_type == AnalysisKind.FUNNEL_RATE:
            summary, evidence, conclusions = self._funnel(dataset)
        elif intent.analysis_type == AnalysisKind.QUALITY:
            summary, evidence, conclusions = self._quality(dataset)
        elif intent.analysis_type == AnalysisKind.CORRELATION:
            summary, evidence, conclusions = self._correlation(dataset, intent)
        elif intent.analysis_type == AnalysisKind.ANOMALY:
            summary, evidence, conclusions = self._anomaly(dataset)
        elif intent.analysis_type == AnalysisKind.SEASONALITY:
            summary, evidence, conclusions = self._seasonality(dataset)
        elif intent.analysis_type == AnalysisKind.PERIOD_COMPARISON:
            summary, evidence, conclusions = self._period_comparison(dataset, intent)
        else:
            summary, evidence, conclusions = self._trend(dataset, intent)
        evidence.insert(0, quality_evidence)
        if join_quality is not None:
            join_evidence = EvidenceRecord(
                id=new_id(),
                title="Cross-source join quality",
                dataset_ids=[dataset.id],
                query_proposal_ids=dataset.query_proposal_ids,
                calculation="Validated DuckDB join quality metrics",
                support=join_quality.model_dump(),
                epistemic_label=EpistemicLabel.CONFIRMED.value,
                confidence=0.95 if not join_quality.weak else 0.6,
                limitations=join_quality.warnings,
            )
            evidence.append(join_evidence)
            if join_quality.weak:
                conclusions.append(
                    Conclusion(
                        text="Join quality is weak; interpret cross-source totals cautiously.",
                        epistemic_label=EpistemicLabel.UNKNOWN.value,
                        evidence_ids=[join_evidence.id],
                    )
                )
        if intent.metadata_confidence == "working_assumption":
            assumption_evidence = EvidenceRecord(
                id=new_id(),
                title="Pilot metric working assumption",
                dataset_ids=[dataset.id],
                query_proposal_ids=dataset.query_proposal_ids,
                calculation="Document-backed draft formula shown in the approved SQL plan",
                support={
                    "metric": intent.metric,
                    "metadata_confidence": intent.metadata_confidence,
                    "assumptions": intent.assumptions,
                },
                epistemic_label=EpistemicLabel.INFERRED.value,
                confidence=0.5,
                limitations=intent.assumptions,
            )
            evidence.append(assumption_evidence)
            conclusions = [
                item.model_copy(
                    update={
                        "epistemic_label": (
                            EpistemicLabel.INFERRED.value
                            if item.epistemic_label == EpistemicLabel.CONFIRMED.value
                            else item.epistemic_label
                        ),
                        "evidence_ids": [*item.evidence_ids, assumption_evidence.id],
                    }
                )
                for item in conclusions
            ]
        return AnalysisComputation(summary=summary, evidence=evidence, conclusions=conclusions)

    def _journey_diagnostic(
        self, dataset: Dataset
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        counts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for row in dataset.rows:
            window = str(row.get("comparison_window", "unknown"))
            stage = str(row.get("exit_stage", "UNKNOWN_STAGE"))
            counts[window][stage] += self._number(row.get("value"))

        def window_summary(window: str) -> dict[str, float | None]:
            stage_counts = counts.get(window, {})
            total = sum(stage_counts.values())
            successful = stage_counts.get("CASE_CREATED", 0.0)
            failed = total - successful
            return {
                "total": total,
                "successful": successful,
                "failed": failed,
                "success_rate": successful / total if total else None,
            }

        baseline = window_summary("baseline")
        incident = window_summary("incident")
        baseline_failed = float(baseline["failed"] or 0.0)
        incident_failed = float(incident["failed"] or 0.0)
        failure_stages = (set(counts.get("baseline", {})) | set(counts.get("incident", {}))) - {
            "CASE_CREATED"
        }
        stage_shifts: dict[str, dict[str, float]] = {}
        for stage in sorted(failure_stages):
            baseline_count = counts.get("baseline", {}).get(stage, 0.0)
            incident_count = counts.get("incident", {}).get(stage, 0.0)
            baseline_share = baseline_count / baseline_failed if baseline_failed else 0.0
            incident_share = incident_count / incident_failed if incident_failed else 0.0
            stage_shifts[stage] = {
                "baseline_count": baseline_count,
                "incident_count": incident_count,
                "baseline_failure_share": baseline_share,
                "incident_failure_share": incident_share,
                "share_change": incident_share - baseline_share,
            }

        baseline_rate = baseline["success_rate"]
        incident_rate = incident["success_rate"]
        rate_change = (
            float(incident_rate) - float(baseline_rate)
            if baseline_rate is not None and incident_rate is not None
            else None
        )
        strongest_stage = (
            max(stage_shifts, key=lambda stage: stage_shifts[stage]["share_change"])
            if stage_shifts
            else None
        )
        pattern_evidence = EvidenceRecord(
            id=new_id(),
            title="Case journey incident comparison",
            dataset_ids=[dataset.id],
            query_proposal_ids=dataset.query_proposal_ids,
            calculation=(
                "Compare successful and failed eligible sessions across baseline and incident "
                f"windows using {self.version}"
            ),
            support={
                "baseline": baseline,
                "incident": incident,
                "success_rate_change": rate_change,
            },
            epistemic_label=EpistemicLabel.CONFIRMED.value,
            confidence=0.95,
            limitations=[
                "Eligibility is a working cohort: visit intent_type='hardware' plus pd_triggered='yes'.",
                "The baseline is a short operational comparison, not a seasonal control.",
            ],
        )
        stage_evidence = EvidenceRecord(
            id=new_id(),
            title="Failed-session last relevant stage distribution",
            dataset_ids=[dataset.id],
            query_proposal_ids=dataset.query_proposal_ids,
            calculation=(
                "For failed sessions, compare the last hardware or flow-related turn by "
                "failure-share change"
            ),
            support={
                "stage_shifts": stage_shifts,
                "largest_share_increase_stage": strongest_stage,
            },
            epistemic_label=EpistemicLabel.CONFIRMED.value,
            confidence=0.85,
            limitations=[
                "The last relevant recorded turn may not equal the user's subjective exit point.",
                "A stage shift localizes the path but does not identify a system root cause.",
            ],
        )
        conclusions: list[Conclusion] = []
        if baseline_rate is not None and incident_rate is not None:
            conclusions.append(
                Conclusion(
                    text=(
                        f"Case success was {float(incident_rate):.1%} in the incident window "
                        f"versus {float(baseline_rate):.1%} in baseline "
                        f"({float(rate_change or 0.0):+.1%} percentage-point change)."
                    ),
                    epistemic_label=EpistemicLabel.CONFIRMED.value,
                    evidence_ids=[pattern_evidence.id],
                )
            )
        if strongest_stage is not None:
            conclusions.append(
                Conclusion(
                    text=(
                        f"{strongest_stage} had the largest observed increase in failed-session "
                        f"share ({stage_shifts[strongest_stage]['share_change']:+.1%})."
                    ),
                    epistemic_label=EpistemicLabel.CONFIRMED.value,
                    evidence_ids=[stage_evidence.id],
                )
            )
        conclusions.append(
            Conclusion(
                text=(
                    "The recorded stage distribution does not by itself establish whether "
                    "PD/KA availability, ticket creation, or user behavior caused the change."
                ),
                epistemic_label=EpistemicLabel.UNKNOWN.value,
                evidence_ids=[pattern_evidence.id, stage_evidence.id],
            )
        )
        return (
            {
                "windows": {"baseline": baseline, "incident": incident},
                "success_rate_change": rate_change,
                "stage_shifts": stage_shifts,
                "largest_share_increase_stage": strongest_stage,
                "next_layer": "bounded_response_theme_review",
            },
            [pattern_evidence, stage_evidence],
            conclusions,
        )

    def _detail(
        self, dataset: Dataset, intent: AnalysisIntent
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        text_values = [
            str(row.get("chat_log_text"))
            for row in dataset.rows
            if row.get("chat_log_text") not in {None, ""}
        ]
        support: dict[str, Any] = {
            "table": intent.detail_table,
            "columns": dataset.columns,
            "rows_returned": dataset.row_count,
            "requested_limit": intent.detail_limit,
        }
        limitations = [
            "Values are displayed as stored; encryption or tokenization is not reversed."
        ]
        if "chat_log_text" in dataset.columns:
            support.update(
                {
                    "non_empty_text_rows": len(text_values),
                    "duplicate_text_rows": len(text_values) - len(set(text_values)),
                    "sample_is_bounded": True,
                }
            )
            limitations.append(
                "Chat text is an untrusted bounded sample; observed themes do not represent the full population."
            )
        evidence = EvidenceRecord(
            id=new_id(),
            title=(
                "Bounded chat text review input"
                if "chat_log_text" in dataset.columns
                else "Bounded UAT detail rows"
            ),
            dataset_ids=[dataset.id],
            query_proposal_ids=dataset.query_proposal_ids,
            calculation="Explicit-column read-only selection with row and byte limits",
            support=support,
            epistemic_label=EpistemicLabel.CONFIRMED.value,
            confidence=1.0,
            limitations=limitations,
        )
        summary: dict[str, Any] = {
            "table": intent.detail_table,
            "rows_returned": dataset.row_count,
            "columns": dataset.columns,
        }
        if "chat_log_text" in dataset.columns:
            summary["source_text_review"] = {
                "evidence_id": evidence.id,
                "rows_reviewed": len(text_values),
                "duplicate_text_rows": len(text_values) - len(set(text_values)),
                "source_text_samples": [value[:2_000] for value in text_values[:20]],
                "trust": "untrusted_source_data",
            }
        conclusion = Conclusion(
            text=(
                f"Prepared {len(text_values)} bounded chat text rows for source-grounded review."
                if "chat_log_text" in dataset.columns
                else f"Returned {dataset.row_count} bounded detail rows from {intent.detail_table}."
            ),
            epistemic_label=EpistemicLabel.CONFIRMED.value,
            evidence_ids=[evidence.id],
        )
        return summary, [evidence], [conclusion]

    def _quality_evidence(self, dataset: Dataset) -> EvidenceRecord:
        return EvidenceRecord(
            id=new_id(),
            title="Dataset completeness and duplication",
            dataset_ids=[dataset.id],
            query_proposal_ids=dataset.query_proposal_ids,
            calculation="missing counts and exact duplicate rows",
            support=dataset.quality.model_dump(),
            epistemic_label=EpistemicLabel.CONFIRMED.value,
            confidence=1.0,
            limitations=[],
        )

    def _trend(
        self, dataset: Dataset, intent: AnalysisIntent
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        if (
            dataset.row_count == 1
            and "period" not in dataset.columns
            and "value" in dataset.columns
        ):
            value = self._number(dataset.rows[0].get("value"))
            evidence = self._calculation_evidence(
                dataset,
                "Scalar calculation",
                {"metric": intent.metric, "value": value},
            )
            return (
                {"value": value},
                [evidence],
                [
                    Conclusion(
                        text=f"The calculated {intent.metric} is {value:,.0f}.",
                        epistemic_label=EpistemicLabel.CONFIRMED.value,
                        evidence_ids=[evidence.id],
                    )
                ],
            )
        series_columns = [
            item for item in intent.dimensions if item != "period" and item in dataset.columns
        ]
        if series_columns:
            grouped: dict[str, list[tuple[str, float]]] = defaultdict(list)
            for row in dataset.rows:
                series = " · ".join(str(row.get(item, "Unknown")) for item in series_columns)
                grouped[series].append((str(row.get("period", "")), self._number(row.get("value"))))
            series_summary: dict[str, dict[str, float | None]] = {}
            for series, observations in grouped.items():
                ordered = sorted(observations, key=lambda item: item[0])
                first = ordered[0][1] if ordered else 0.0
                last = ordered[-1][1] if ordered else 0.0
                change = last - first
                series_summary[series] = {
                    "first": first,
                    "last": last,
                    "change": change,
                    "change_pct": None if first == 0 else change / first,
                }
            evidence = self._calculation_evidence(
                dataset,
                "Trend calculation by series",
                {"series_dimensions": series_columns, "series": series_summary},
            )
            return (
                {"series": series_summary},
                [evidence],
                [
                    Conclusion(
                        text=(
                            f"Returned {len(series_summary)} observed series by "
                            + ", ".join(series_columns)
                            + "."
                        ),
                        epistemic_label=EpistemicLabel.CONFIRMED.value,
                        evidence_ids=[evidence.id],
                    )
                ],
            )

        values = self._numbers(dataset, "value")
        first, last = (values[0], values[-1]) if values else (0.0, 0.0)
        change = last - first
        change_pct = None if first == 0 else change / first
        evidence = self._calculation_evidence(
            dataset,
            "Trend calculation",
            {"first": first, "last": last, "change": change, "change_pct": change_pct},
        )
        direction = "increased" if change > 0 else "decreased" if change < 0 else "was flat"
        return (
            {"first": first, "last": last, "change": change, "change_pct": change_pct},
            [evidence],
            [
                Conclusion(
                    text=f"The metric {direction} by {change:,.2f} across the observed periods.",
                    epistemic_label=EpistemicLabel.CONFIRMED.value,
                    evidence_ids=[evidence.id],
                )
            ],
        )

    def _period_comparison(
        self, dataset: Dataset, intent: AnalysisIntent
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        return self._trend(dataset, intent)

    def _segment(
        self, dataset: Dataset, intent: AnalysisIntent
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        dimension_columns = [item for item in intent.dimensions if item in dataset.columns]
        totals: dict[str, float] = defaultdict(float)
        for row in dataset.rows:
            if dimension_columns:
                key = " · ".join(str(row.get(item, "Unknown")) for item in dimension_columns)
            else:
                key = str(row.get("segment", "Unknown"))
            totals[key] += self._number(row.get("value"))
        evidence = self._calculation_evidence(dataset, "Segment totals", {"totals": totals})
        leader = max(totals, key=lambda item: totals[item]) if totals else "Unknown"
        return (
            {"segment_totals": totals},
            [evidence],
            [
                Conclusion(
                    text=f"{leader} is the largest observed segment.",
                    epistemic_label=EpistemicLabel.CONFIRMED.value,
                    evidence_ids=[evidence.id],
                )
            ],
        )

    def _contribution(
        self, dataset: Dataset
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        totals: dict[str, float] = defaultdict(float)
        for row in dataset.rows:
            totals[str(row.get("segment", "Unknown"))] += self._number(row.get("value"))
        total = sum(totals.values())
        shares = {key: (value / total if total else 0.0) for key, value in totals.items()}
        reconciliation_gap = total - sum(totals.values())
        evidence = self._calculation_evidence(
            dataset,
            "Contribution analysis",
            {
                "component_totals": totals,
                "shares": shares,
                "total": total,
                "reconciliation_gap": reconciliation_gap,
                "function_version": self.version,
            },
        )
        leader = max(shares, key=lambda item: shares[item]) if shares else "Unknown"
        return (
            {
                "component_totals": totals,
                "shares": shares,
                "total": total,
                "reconciliation_gap": reconciliation_gap,
            },
            [evidence],
            [
                Conclusion(
                    text=f"{leader} contributed the largest calculated share ({shares.get(leader, 0):.1%}).",
                    epistemic_label=EpistemicLabel.CONFIRMED.value,
                    evidence_ids=[evidence.id],
                )
            ],
        )

    def _funnel(
        self, dataset: Dataset
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        visitors = sum(self._number(row.get("visitors")) for row in dataset.rows)
        conversions = sum(self._number(row.get("conversions")) for row in dataset.rows)
        rate = conversions / visitors if visitors else None
        evidence = self._calculation_evidence(
            dataset,
            "Funnel rate",
            {"numerator": conversions, "denominator": visitors, "rate": rate},
        )
        text = (
            "The bounded funnel rate is unknown because the denominator is zero."
            if rate is None
            else f"The bounded funnel conversion rate is {rate:.2%}."
        )
        label = EpistemicLabel.UNKNOWN.value if rate is None else EpistemicLabel.CONFIRMED.value
        return (
            {"numerator": conversions, "denominator": visitors, "rate": rate},
            [evidence],
            [Conclusion(text=text, epistemic_label=label, evidence_ids=[evidence.id])],
        )

    def _quality(
        self, dataset: Dataset
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        support = dataset.quality.model_dump()
        evidence = self._calculation_evidence(dataset, "Quality checks", support)
        issue_count = dataset.quality.duplicate_rows + sum(
            dataset.quality.missing_by_column.values()
        )
        return (
            support,
            [evidence],
            [
                Conclusion(
                    text=f"Detected {issue_count} bounded completeness/duplicate issue(s).",
                    epistemic_label=EpistemicLabel.CONFIRMED.value,
                    evidence_ids=[evidence.id],
                )
            ],
        )

    def _correlation(
        self, dataset: Dataset, intent: AnalysisIntent
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        pairs = [
            (self._number(row.get("spend")), self._number(row.get("revenue")))
            for row in dataset.rows
            if row.get("spend") is not None and row.get("revenue") is not None
        ]
        coefficient = self._pearson(pairs)
        support = {
            "coefficient": coefficient,
            "pairs": len(pairs),
            "causal_design": intent.causal_design,
        }
        evidence = EvidenceRecord(
            id=new_id(),
            title="Correlation calculation",
            dataset_ids=[dataset.id],
            query_proposal_ids=dataset.query_proposal_ids,
            calculation="Pearson correlation over bounded joined rows",
            support=support,
            epistemic_label=EpistemicLabel.INFERRED.value,
            confidence=0.55,
            limitations=["Correlation does not establish causation.", "Small demo sample."],
        )
        text = f"Spend and revenue have an observed correlation of {coefficient:.3f}; this is inferred association, not a causal effect."
        return (
            support,
            [evidence],
            [
                Conclusion(
                    text=text,
                    epistemic_label=EpistemicLabel.INFERRED.value,
                    evidence_ids=[evidence.id],
                )
            ],
        )

    def _anomaly(
        self, dataset: Dataset
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        values = self._numbers(dataset, "value")
        mean = fmean(values) if values else 0.0
        deviation = pstdev(values) if len(values) > 1 else 0.0
        anomalies = [
            index
            for index, value in enumerate(values)
            if deviation and abs(value - mean) / deviation >= 2
        ]
        support = {
            "mean": mean,
            "population_stddev": deviation,
            "anomaly_indexes": anomalies,
            "threshold_z": 2,
        }
        evidence = self._calculation_evidence(dataset, "Basic anomaly detection", support)
        return (
            support,
            [evidence],
            [
                Conclusion(
                    text=f"Detected {len(anomalies)} basic z-score anomaly candidate(s).",
                    epistemic_label=EpistemicLabel.CONFIRMED.value,
                    evidence_ids=[evidence.id],
                )
            ],
        )

    def _seasonality(
        self, dataset: Dataset
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        values = self._numbers(dataset, "value")
        support = {"periods": len(values), "range": (max(values) - min(values)) if values else 0.0}
        evidence = EvidenceRecord(
            id=new_id(),
            title="Seasonality hypothesis",
            dataset_ids=[dataset.id],
            query_proposal_ids=dataset.query_proposal_ids,
            calculation="calendar-pattern hypothesis over bounded periods",
            support=support,
            epistemic_label=EpistemicLabel.INFERRED.value,
            confidence=0.4,
            limitations=[
                "A longer history and calendar controls are required to confirm seasonality."
            ],
        )
        return (
            support,
            [evidence],
            [
                Conclusion(
                    text="The observed calendar pattern is a hypothesis and needs a longer controlled history.",
                    epistemic_label=EpistemicLabel.INFERRED.value,
                    evidence_ids=[evidence.id],
                )
            ],
        )

    def _calculation_evidence(
        self, dataset: Dataset, title: str, support: dict[str, Any]
    ) -> EvidenceRecord:
        return EvidenceRecord(
            id=new_id(),
            title=title,
            dataset_ids=[dataset.id],
            query_proposal_ids=dataset.query_proposal_ids,
            calculation=f"{title} using {self.version}",
            support=support,
            epistemic_label=EpistemicLabel.CONFIRMED.value,
            confidence=0.95,
            limitations=[],
        )

    @staticmethod
    def _number(value: Any) -> float:
        if value is None:
            return 0.0
        try:
            number = float(value)
            return number if math.isfinite(number) else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _numbers(self, dataset: Dataset, column: str) -> list[float]:
        return [self._number(row.get(column)) for row in dataset.rows]

    @staticmethod
    def _pearson(pairs: list[tuple[float, float]]) -> float:
        if len(pairs) < 2:
            return 0.0
        xs, ys = zip(*pairs, strict=True)
        x_mean, y_mean = fmean(xs), fmean(ys)
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
        denominator = math.sqrt(
            sum((x - x_mean) ** 2 for x in xs) * sum((y - y_mean) ** 2 for y in ys)
        )
        return 0.0 if denominator == 0 else numerator / denominator
