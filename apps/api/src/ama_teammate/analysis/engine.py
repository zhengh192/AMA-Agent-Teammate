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
        quality_evidence = self._quality_evidence(dataset, intent.response_language)
        if intent.analysis_type == AnalysisKind.JOURNEY_DIAGNOSTIC:
            summary, evidence, conclusions = self._journey_diagnostic(dataset, intent)
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
        self, dataset: Dataset, intent: AnalysisIntent
    ) -> tuple[dict[str, Any], list[EvidenceRecord], list[Conclusion]]:
        contract = intent.journey_diagnostic_contract
        if contract is None:
            raise ValueError("Journey diagnostic Skill contract is missing.")
        hierarchy = [item.key for item in contract.hierarchy]
        labels = {
            item.key: (
                item.label_zh if intent.response_language == "zh-CN" else item.label_en
            )
            for item in contract.hierarchy
        }
        daily: dict[
            str,
            dict[str, dict[tuple[str, tuple[str, ...]], float]],
        ] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        distribution_rows = [
            row for row in dataset.rows if row.get("record_type") in {None, "", "distribution"}
        ]
        response_rows: list[dict[str, Any]] = []
        for row in dataset.rows:
            for key, response in row.items():
                suffix = key.removeprefix("bot_response_")
                if suffix == key or not suffix.isdigit() or response in {None, ""}:
                    continue
                response_rows.append({**row, "bot_response": str(response)})
        for row in distribution_rows:
            window = str(row.get("comparison_window", "unknown"))
            comparison_date = str(row.get("comparison_date", "unknown"))
            outcome = str(row.get("outcome", "FAILED"))
            path = tuple(
                str(row.get(key) or f"UNKNOWN_{key.upper()}") for key in hierarchy
            )
            daily[window][comparison_date][(outcome, path)] += self._number(row.get("value"))

        def window_summary(window: str) -> dict[str, Any]:
            dates = sorted(daily.get(window, {}))
            daily_totals: list[float] = []
            daily_successes: list[float] = []
            daily_failures: list[float] = []
            daily_rates: list[float] = []
            for comparison_date in dates:
                rows = daily[window][comparison_date]
                successful = sum(
                    value for (outcome, _), value in rows.items() if outcome == "CASE_CREATED"
                )
                failed = sum(value for (outcome, _), value in rows.items() if outcome != "CASE_CREATED")
                total = successful + failed
                daily_totals.append(total)
                daily_successes.append(successful)
                daily_failures.append(failed)
                if total:
                    daily_rates.append(successful / total)
            return {
                "dates": dates,
                "days": len(dates),
                "total": sum(daily_totals),
                "successful": sum(daily_successes),
                "failed": sum(daily_failures),
                "average_daily_total": fmean(daily_totals) if daily_totals else 0.0,
                "average_daily_successful": (
                    fmean(daily_successes) if daily_successes else 0.0
                ),
                "average_daily_failed": fmean(daily_failures) if daily_failures else 0.0,
                "success_rate": fmean(daily_rates) if daily_rates else None,
            }

        baseline = window_summary("baseline")
        incident = window_summary("incident")

        def breakdown(level_index: int, parents: tuple[str, ...]) -> list[dict[str, Any]]:
            values: set[str] = set()
            for window_rows in daily.values():
                for day_rows in window_rows.values():
                    for (outcome, path), _ in day_rows.items():
                        if outcome == "CASE_CREATED" or path[:level_index] != parents:
                            continue
                        values.add(path[level_index])

            rows: list[dict[str, Any]] = []
            for value in values:
                metrics: dict[str, float] = {}
                for window in ("baseline", "incident"):
                    counts: list[float] = []
                    shares: list[float] = []
                    for comparison_date in sorted(daily.get(window, {})):
                        count = 0.0
                        denominator = 0.0
                        for (outcome, path), amount in daily[window][comparison_date].items():
                            if outcome == "CASE_CREATED" or path[:level_index] != parents:
                                continue
                            denominator += amount
                            if path[level_index] == value:
                                count += amount
                        counts.append(count)
                        shares.append(count / denominator if denominator else 0.0)
                    metrics[f"{window}_average_daily_count"] = (
                        fmean(counts) if counts else 0.0
                    )
                    metrics[f"{window}_average_daily_share"] = (
                        fmean(shares) if shares else 0.0
                    )
                rows.append(
                    {
                        "value": value,
                        "baseline_average_daily_count": metrics[
                            "baseline_average_daily_count"
                        ],
                        "incident_average_daily_count": metrics[
                            "incident_average_daily_count"
                        ],
                        "excess_failed_sessions": (
                            metrics["incident_average_daily_count"]
                            - metrics["baseline_average_daily_count"]
                        ),
                        "baseline_failure_share": metrics[
                            "baseline_average_daily_share"
                        ],
                        "incident_failure_share": metrics[
                            "incident_average_daily_share"
                        ],
                        "failure_share_change": (
                            metrics["incident_average_daily_share"]
                            - metrics["baseline_average_daily_share"]
                        ),
                    }
                )
            rank_by = contract.rank_by
            return sorted(
                rows,
                key=lambda item: (
                    float(item[rank_by]),
                    float(item["incident_average_daily_count"]),
                    str(item["value"]),
                ),
                reverse=True,
            )

        levels: list[dict[str, Any]] = []
        parent_values: list[str] = []
        for level_index, key in enumerate(hierarchy):
            level_contract = contract.hierarchy[level_index]
            incident_total = 0.0
            incident_known = 0.0
            for day_rows in daily.get("incident", {}).values():
                for (outcome, path), amount in day_rows.items():
                    if outcome == "CASE_CREATED" or path[:level_index] != tuple(parent_values):
                        continue
                    incident_total += amount
                    if not path[level_index].startswith("UNKNOWN_"):
                        incident_known += amount
            coverage = incident_known / incident_total if incident_total else 0.0
            if not level_contract.required and coverage < level_contract.minimum_coverage:
                levels.append(
                    {
                        "key": key,
                        "label": labels[key],
                        "parent": {
                            hierarchy[index]: value for index, value in enumerate(parent_values)
                        },
                        "rows": [],
                        "display_rows": [],
                        "selected": None,
                        "coverage": coverage,
                        "minimum_coverage": level_contract.minimum_coverage,
                        "skipped_reason": "coverage_below_threshold",
                    }
                )
                break
            rows = breakdown(level_index, tuple(parent_values))
            selected: str | None = None
            if rows:
                candidate = rows[0]
                rank_value = float(candidate[contract.rank_by])
                incident_count = float(candidate["incident_average_daily_count"])
                if (
                    not contract.drill_down_only_positive_parent or rank_value > 0
                ) and incident_count >= contract.small_sample_threshold:
                    selected = str(candidate["value"])
            levels.append(
                {
                    "key": key,
                    "label": labels[key],
                    "parent": {
                        hierarchy[index]: value for index, value in enumerate(parent_values)
                    },
                    "rows": rows,
                    "display_rows": rows[: contract.show_top_n],
                    "selected": selected,
                    "coverage": coverage,
                    "minimum_coverage": level_contract.minimum_coverage,
                    "skipped_reason": None,
                }
            )
            if selected is None:
                break
            parent_values.append(selected)

        baseline_rate = baseline["success_rate"]
        incident_rate = incident["success_rate"]
        rate_change = (
            float(incident_rate) - float(baseline_rate)
            if baseline_rate is not None and incident_rate is not None
            else None
        )
        first_level_rows = levels[0]["rows"] if levels else []
        strongest_stage = (
            str(levels[0]["selected"]) if levels and levels[0]["selected"] is not None else None
        )
        stage_shifts = {
            str(row["value"]): {
                "baseline_count": row["baseline_average_daily_count"],
                "incident_count": row["incident_average_daily_count"],
                "baseline_failure_share": row["baseline_failure_share"],
                "incident_failure_share": row["incident_failure_share"],
                "share_change": row["failure_share_change"],
                "excess_failed_sessions": row["excess_failed_sessions"],
            }
            for row in first_level_rows
        }
        chinese = intent.response_language == "zh-CN"
        pattern_evidence = EvidenceRecord(
            id=new_id(),
            title="建单成功率与日均基线对比" if chinese else "Case success versus daily baseline",
            dataset_ids=[dataset.id],
            query_proposal_ids=dataset.query_proposal_ids,
            calculation=(
                "按自然日计算建单成功率，并将异常期与基线期每日结果的平均值比较。"
                if chinese
                else "Calculate daily case success rates and compare the incident with the mean daily baseline."
            ),
            support={
                "baseline": baseline,
                "incident": incident,
                "success_rate_change": rate_change,
            },
            epistemic_label=EpistemicLabel.CONFIRMED.value,
            confidence=0.95,
            limitations=[
                (
                    "当前基线是紧邻异常日前的短期日均，不是季节性对照。"
                    if chinese
                    else "The baseline is a short adjacent daily average, not a seasonal control."
                )
            ],
        )
        hierarchy_evidence: list[EvidenceRecord] = []
        for level in levels:
            hierarchy_evidence.append(
                EvidenceRecord(
                    id=new_id(),
                    title=(
                        f"{level['label']}离开分布与基线增量"
                        if chinese
                        else f"{level['label']} exit distribution versus baseline"
                    ),
                    dataset_ids=[dataset.id],
                    query_proposal_ids=dataset.query_proposal_ids,
                    calculation=(
                        "比较失败 session 在该层级的异常期日均数量、基线日均数量、增量和条件占比变化。"
                        if chinese
                        else (
                            "Compare incident daily count, baseline daily count, excess failures, "
                            "and conditional share change at this hierarchy level."
                        )
                    ),
                    support=level,
                    epistemic_label=EpistemicLabel.CONFIRMED.value,
                    confidence=0.9,
                    limitations=[
                        (
                            "最后记录的阶段用于定位离开位置，但不等同于已经证明的系统根因。"
                            if chinese
                            else (
                                "The last recorded stage localizes the exit point but does not "
                                "prove a system root cause."
                            )
                        )
                    ],
                )
            )

        response_evidence_record: EvidenceRecord | None = None
        response_evidence_summary: dict[str, Any] | None = None
        response_contract = contract.response_evidence
        if (
            response_contract is not None
            and response_contract.enabled
            and parent_values
            and response_rows
        ):
            selected_path = {hierarchy[index]: value for index, value in enumerate(parent_values)}
            samples: dict[str, list[dict[str, Any]]] = {
                "incident": [],
                "baseline": [],
            }
            seen: dict[str, set[str]] = {"incident": set(), "baseline": set()}
            for row in response_rows:
                window = str(row.get("comparison_window", ""))
                if window not in samples:
                    continue
                if window == "baseline" and not response_contract.compare_with_baseline:
                    continue
                if any(
                    str(row.get(key) or f"UNKNOWN_{key.upper()}") != value
                    for key, value in selected_path.items()
                ):
                    continue
                response = str(row.get("bot_response") or "").strip()
                if not response or response in seen[window]:
                    continue
                if len(samples[window]) >= response_contract.max_responses_per_bucket:
                    continue
                seen[window].add(response)
                samples[window].append(
                    {
                        "comparison_date": (
                            str(row["comparison_date"])
                            if row.get("comparison_date") is not None
                            else None
                        ),
                        "agent_stage": row.get("agent_stage"),
                        "symptom": row.get("symptom"),
                        "flow_step": row.get("flow_step"),
                        "bot_response": response[: response_contract.max_response_characters],
                    }
                )
            response_evidence_summary = {
                "selected_path": selected_path,
                "incident_sample_count": len(samples["incident"]),
                "baseline_sample_count": len(samples["baseline"]),
                "samples": samples,
                "bounded_examples_only": True,
            }
            if samples["incident"] or samples["baseline"]:
                response_evidence_record = EvidenceRecord(
                    id=new_id(),
                    title=(
                        "\u79bb\u5f00\u4f4d\u7f6e\u7684 Bot \u56de\u590d\u8bc1\u636e"
                        if chinese
                        else "Bot-response evidence at the exit location"
                    ),
                    dataset_ids=[dataset.id],
                    query_proposal_ids=dataset.query_proposal_ids,
                    calculation=(
                        "\u5728\u5df2\u5b9a\u4f4d\u7684\u5931\u8d25 session \u4e2d\uff0c\u5bf9\u6bd4\u5f02\u5e38\u671f\u4e0e\u57fa\u7ebf\u671f\u6700\u540e\u76f8\u5173\u8f6e\u6b21\u7684\u6709\u754c bot_response \u6837\u672c\u3002"
                        if chinese
                        else (
                            "Compare bounded last-relevant-turn bot_response samples for the "
                            "localized failed-session cohort in incident and baseline windows."
                        )
                    ),
                    support=response_evidence_summary,
                    epistemic_label=EpistemicLabel.CONFIRMED.value,
                    confidence=0.85,
                    limitations=[
                        (
                            "\u8fd9\u4e9b\u662f\u6709\u754c\u6837\u672c\uff0c\u7528\u4e8e\u8f85\u52a9\u4eba\u5de5\u5224\u65ad\uff0c\u4e0d\u4ee3\u8868\u5168\u91cf\u8bdd\u672f\u5206\u5e03\uff0c\u4e5f\u4e0d\u80fd\u5355\u72ec\u8bc1\u660e\u6839\u56e0\u3002"
                            if chinese
                            else (
                                "These bounded examples support human diagnosis; they are not "
                                "a full theme distribution and do not independently prove cause."
                            )
                        )
                    ],
                )

        def count_text(value: float) -> str:
            return f"{value:.1f}".rstrip("0").rstrip(".")

        conclusions: list[Conclusion] = []
        if baseline_rate is not None and incident_rate is not None:
            if chinese:
                incident_date = "、".join(incident["dates"]) or "异常期"
                movement = (
                    f"{incident_date} 建单成功率为 {float(incident_rate):.1%}，"
                    f"基线日均为 {float(baseline_rate):.1%}，"
                    f"变化 {float(rate_change or 0.0) * 100:+.1f} 个百分点。"
                )
            else:
                movement = (
                    f"Case success was {float(incident_rate):.1%} in the incident window "
                    f"versus a {float(baseline_rate):.1%} mean daily baseline "
                    f"({float(rate_change or 0.0) * 100:+.1f} percentage points)."
                )
            conclusions.append(
                Conclusion(
                    text=movement,
                    epistemic_label=EpistemicLabel.CONFIRMED.value,
                    evidence_ids=[pattern_evidence.id],
                )
            )

        for index, level in enumerate(levels):
            rows = level["display_rows"]
            if not rows:
                continue
            parts = [
                (
                    f"{row['value']}：异常期日均 {count_text(float(row['incident_average_daily_count']))}，"
                    f"基线日均 {count_text(float(row['baseline_average_daily_count']))}，"
                    f"多 {count_text(float(row['excess_failed_sessions']))} 个"
                    if chinese
                    else (
                        f"{row['value']}: incident {count_text(float(row['incident_average_daily_count']))}, "
                        f"baseline {count_text(float(row['baseline_average_daily_count']))}, "
                        f"excess {count_text(float(row['excess_failed_sessions']))}"
                    )
                )
                for row in rows[:3]
            ]
            if chinese:
                if index == 0:
                    text = "先看全部 Agent 阶段，增量最大的几项是：" + "；".join(parts) + "。"
                else:
                    parent = " / ".join(str(value) for value in level["parent"].values())
                    text = (
                        f"只在 {parent} 内继续下钻 {level['label']}："
                        + "；".join(parts)
                        + "。"
                    )
            else:
                parent = " / ".join(str(value) for value in level["parent"].values())
                prefix = (
                    "Across all Agent stages, the largest increases were: "
                    if index == 0
                    else f"Within {parent}, the {level['label']} drill-down was: "
                )
                text = prefix + "; ".join(parts) + "."
            conclusions.append(
                Conclusion(
                    text=text,
                    epistemic_label=EpistemicLabel.CONFIRMED.value,
                    evidence_ids=[hierarchy_evidence[index].id],
                )
            )

        conclusions.append(
            Conclusion(
                text=(
                    "这些分布可以确认异常集中在哪个 Agent 阶段、症状和步骤，但仅凭时序与集中度还不能确认 PD/KA、建单接口或用户行为就是根因。"
                    if chinese
                    else (
                        "These distributions locate the stage, symptom, and step where the "
                        "increase concentrated. This evidence does not prove whether PD/KA, "
                        "ticket creation, or user behavior caused it."
                    )
                ),
                epistemic_label=EpistemicLabel.UNKNOWN.value,
                evidence_ids=[
                    pattern_evidence.id,
                    *[item.id for item in hierarchy_evidence],
                ][:10],
            )
        )
        if response_evidence_record is not None:
            conclusions.append(
                Conclusion(
                    text=(
                        "\u5df2\u5728\u6700\u6df1\u53ef\u9760\u7684\u79bb\u5f00\u4f4d\u7f6e\u9644\u4e0a\u5f02\u5e38\u671f\u4e0e\u57fa\u7ebf\u671f\u7684 Bot \u56de\u590d\u6837\u672c\uff0c\u4f9b\u4eba\u5de5\u5224\u65ad\u95ee\u9898\u573a\u666f\u3002"
                        if chinese
                        else (
                            "Bounded incident and baseline bot-response samples are attached at "
                            "the deepest reliable exit location for human diagnosis."
                        )
                    ),
                    epistemic_label=EpistemicLabel.CONFIRMED.value,
                    evidence_ids=[response_evidence_record.id],
                )
            )
        return (
            {
                "response_language": intent.response_language,
                "windows": {"baseline": baseline, "incident": incident},
                "success_rate_change": rate_change,
                "hierarchy": levels,
                "stage_shifts": stage_shifts,
                "largest_share_increase_stage": strongest_stage,
                "response_evidence": response_evidence_summary,
                "next_layer": (
                    "response_evidence_attached"
                    if response_evidence_record is not None
                    else "response_evidence_unavailable"
                ),
                "skill_contract": contract.model_dump(mode="json"),
            },
            [
                pattern_evidence,
                *hierarchy_evidence,
                *([response_evidence_record] if response_evidence_record is not None else []),
            ],
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

    def _quality_evidence(
        self, dataset: Dataset, response_language: str = "en"
    ) -> EvidenceRecord:
        chinese = response_language == "zh-CN"
        return EvidenceRecord(
            id=new_id(),
            title="数据完整性与重复检查" if chinese else "Dataset completeness and duplication",
            dataset_ids=[dataset.id],
            query_proposal_ids=dataset.query_proposal_ids,
            calculation=(
                "统计缺失值和完全重复行"
                if chinese
                else "missing counts and exact duplicate rows"
            ),
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
