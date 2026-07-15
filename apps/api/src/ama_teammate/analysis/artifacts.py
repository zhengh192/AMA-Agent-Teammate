from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

from ama_teammate.analysis.models import Dataset
from ama_teammate.domain.models import new_id


class CSVArtifactWriter:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, run_id: str, dataset: Dataset) -> tuple[str, Path, str]:
        artifact_id = new_id()
        run_root = (self.root / run_id).resolve()
        artifact_root = self.root.resolve()
        if not run_root.is_relative_to(artifact_root):
            raise ValueError("Artifact path escaped configured root")
        run_root.mkdir(parents=True, exist_ok=True)
        path = run_root / f"{artifact_id}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=dataset.columns, extrasaction="ignore")
            writer.writeheader()
            for row in dataset.rows:
                writer.writerow(
                    {column: self._safe_cell(row.get(column)) for column in dataset.columns}
                )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return artifact_id, path, digest

    @staticmethod
    def _safe_cell(value: Any) -> Any:
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
            return "'" + value
        return value
