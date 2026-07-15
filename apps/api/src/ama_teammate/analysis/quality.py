from __future__ import annotations

from collections import Counter
from typing import Any

from ama_teammate.analysis.models import DatasetQuality


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
    return DatasetQuality(
        row_count=len(rows),
        missing_by_column=missing,
        duplicate_rows=duplicate_rows,
        warnings=warnings,
    )


def _stable_value(value: Any) -> str:
    return "<NULL>" if value is None else str(value)
