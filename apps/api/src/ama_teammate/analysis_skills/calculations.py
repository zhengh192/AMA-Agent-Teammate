from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CalculationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChangeResult(CalculationModel):
    absolute_change: float
    percentage_point_change: float | None
    relative_change: float | None


class DecompositionResult(CalculationModel):
    total_change: float
    mix_effect: float
    rate_effect: float
    interaction_effect: float
    reconciliation_gap: float


class FunnelResult(CalculationModel):
    conversion_rate: float | None
    drop_off_count: float
    drop_off_rate: float | None


class QualityCheckResult(CalculationModel):
    row_count: int
    null_rates: dict[str, float]
    duplicate_rows: int


class FreshnessResult(CalculationModel):
    age_seconds: float | None
    fresh: bool | None
    warning: str | None = None


class MatchRateResult(CalculationModel):
    matched: int
    left_total: int
    match_rate: float | None
    unmatched_rate: float | None


def calculate_change(previous: float, current: float, *, is_rate: bool = False) -> ChangeResult:
    relative = None if previous == 0 else (current - previous) / abs(previous)
    return ChangeResult(
        absolute_change=current - previous,
        percentage_point_change=(current - previous) * 100 if is_rate else None,
        relative_change=relative,
    )


def compare_periods(previous: list[float], current: list[float], *, is_rate: bool = False) -> ChangeResult:
    return calculate_change(sum(previous), sum(current), is_rate=is_rate)


def calculate_contributions(changes: dict[str, float]) -> dict[str, float | None]:
    total = sum(changes.values())
    return {key: None if total == 0 else value / total for key, value in changes.items()}


def decompose_mix_rate(
    previous_weights: dict[str, float],
    previous_rates: dict[str, float],
    current_weights: dict[str, float],
    current_rates: dict[str, float],
) -> DecompositionResult:
    segments = set(previous_weights) | set(previous_rates) | set(current_weights) | set(current_rates)
    previous_total = sum(previous_weights.get(s, 0) * previous_rates.get(s, 0) for s in segments)
    current_total = sum(current_weights.get(s, 0) * current_rates.get(s, 0) for s in segments)
    mix = sum((current_weights.get(s, 0) - previous_weights.get(s, 0)) * previous_rates.get(s, 0) for s in segments)
    rate = sum(previous_weights.get(s, 0) * (current_rates.get(s, 0) - previous_rates.get(s, 0)) for s in segments)
    interaction = sum(
        (current_weights.get(s, 0) - previous_weights.get(s, 0))
        * (current_rates.get(s, 0) - previous_rates.get(s, 0))
        for s in segments
    )
    change = current_total - previous_total
    return DecompositionResult(
        total_change=change,
        mix_effect=mix,
        rate_effect=rate,
        interaction_effect=interaction,
        reconciliation_gap=change - mix - rate - interaction,
    )


def calculate_funnel(entered: float, completed: float) -> FunnelResult:
    return FunnelResult(
        conversion_rate=None if entered == 0 else completed / entered,
        drop_off_count=entered - completed,
        drop_off_rate=None if entered == 0 else (entered - completed) / entered,
    )


def check_nulls_and_duplicates(rows: list[dict[str, Any]]) -> QualityCheckResult:
    columns = sorted({key for row in rows for key in row})
    null_rates = {
        column: (sum(row.get(column) is None for row in rows) / len(rows) if rows else 0.0)
        for column in columns
    }
    fingerprints = [tuple(str(row.get(column)) for column in columns) for row in rows]
    duplicates = sum(count - 1 for count in Counter(fingerprints).values() if count > 1)
    return QualityCheckResult(row_count=len(rows), null_rates=null_rates, duplicate_rows=duplicates)


def check_freshness(
    latest_timestamp: datetime | None,
    max_age_seconds: float,
    *,
    now: datetime | None = None,
) -> FreshnessResult:
    if latest_timestamp is None:
        return FreshnessResult(age_seconds=None, fresh=None, warning="Latest timestamp is unknown.")
    reference = now or datetime.now(UTC)
    timestamp = latest_timestamp if latest_timestamp.tzinfo else latest_timestamp.replace(tzinfo=UTC)
    age = max(0.0, (reference - timestamp).total_seconds())
    return FreshnessResult(age_seconds=age, fresh=age <= max_age_seconds)


def calculate_match_rate(left_keys: list[Any], right_keys: list[Any]) -> MatchRateResult:
    right = {str(value) for value in right_keys if value is not None}
    matched = sum(str(value) in right for value in left_keys if value is not None)
    total = len(left_keys)
    rate = None if total == 0 else matched / total
    return MatchRateResult(
        matched=matched,
        left_total=total,
        match_rate=rate,
        unmatched_rate=None if rate is None else 1 - rate,
    )

def check_volume_anomaly(
    current_count: int, baseline_count: int, max_relative_change: float = 0.5
) -> bool:
    if baseline_count == 0:
        return current_count != 0
    return abs(current_count - baseline_count) / baseline_count > max_relative_change


def check_schema_consistency(
    actual_columns: set[str], expected_columns: set[str]
) -> dict[str, list[str]]:
    return {
        "missing_columns": sorted(expected_columns - actual_columns),
        "unexpected_columns": sorted(actual_columns - expected_columns),
    }


def calculate_referential_integrity(
    child_keys: list[Any], parent_keys: list[Any]
) -> float | None:
    bounded_children = [str(value) for value in child_keys if value is not None]
    if not bounded_children:
        return None
    parents = {str(value) for value in parent_keys if value is not None}
    return sum(value in parents for value in bounded_children) / len(bounded_children)


def check_period_coverage(
    actual_periods: list[str], expected_periods: list[str]
) -> dict[str, list[str] | bool]:
    missing = sorted(set(expected_periods) - set(actual_periods))
    return {
        "complete": not missing,
        "missing_periods": missing,
    }



def small_sample_warning(sample_size: int, threshold: int = 30) -> str | None:
    return f"Small sample: {sample_size} observations; minimum is {threshold}." if sample_size < threshold else None


def reconciliation_gap(total_change: float, components: list[float]) -> float:
    return total_change - sum(components)
