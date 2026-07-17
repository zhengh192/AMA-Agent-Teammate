from __future__ import annotations

from collections import Counter
from typing import Any

from ama_teammate.analysis.models import DataConfidence, DatasetQuality


def assess_dataset_quality(rows: list[dict[str, Any]], columns: list[str]) -> DatasetQuality:
    missing = {column: sum(row.get(column) is None for row in rows) for column in columns}
    fingerprints = [tuple(_stable_value(row.get(column)) for column in columns) for row in rows]
    duplicate_rows = sum(count - 1 for count in Counter(fingerprints).values() if count > 1)
    warnings: list[str] = []
    if duplicate_rows:
        warnings.append(f"Detected {duplicate_rows} duplicate row(s).")
    missing_total = sum(missing.values())
    if missing_total:
        warnings.append(f"Detected {missing_total} null value(s).")
    cell_count = max(1, len(rows) * len(columns))
    completeness = 1 - missing_total / cell_count
    uniqueness = 1 - duplicate_rows / max(1, len(rows))
    if not rows or completeness < 0.5:
        confidence = DataConfidence.UNUSABLE
    elif completeness < 0.9 or uniqueness < 0.8:
        confidence = DataConfidence.LOW
    elif missing_total or duplicate_rows:
        confidence = DataConfidence.MEDIUM
    else:
        confidence = DataConfidence.HIGH
    return DatasetQuality(
        row_count=len(rows),
        missing_by_column=missing,
        duplicate_rows=duplicate_rows,
        warnings=warnings,
        completeness_rate=completeness,
        uniqueness_rate=uniqueness,
        confidence=confidence,
    )


def _stable_value(value: Any) -> str:
    return "<NULL>" if value is None else str(value)
