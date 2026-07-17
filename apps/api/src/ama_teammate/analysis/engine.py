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
        if intent.analysis_type == AnalysisKind.CONTRIBUTION:
            summary, evidence, conclusions = self._contribution(dataset)
        elif intent.analysis_type == AnalysisKind.SEGMENT_BREAKDOWN:
            summary, evidence, conclusions = self._segment(dataset)
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
            summary, evidence, conclusions = self._period_comparison(dataset)
        else:
            summary, evidence, conclusions = self._trend(dataset)
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
        self, dataset: Dataset
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
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
        self, dataset: Dataset
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        return self._trend(dataset)

    def _segment(
        self, dataset: Dataset
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        totals: dict[str, float] = defaultdict(float)
        for row in dataset.rows:
            totals[str(row.get("segment", "Unknown"))] += self._number(row.get("value"))
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
