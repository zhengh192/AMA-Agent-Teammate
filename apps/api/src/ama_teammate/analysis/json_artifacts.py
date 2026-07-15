from __future__ import annotations

import hashlib
from pathlib import Path

from ama_teammate.analysis.models import AnalysisResult
from ama_teammate.domain.models import new_id


class JSONArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write_result(self, result: AnalysisResult) -> tuple[str, Path, str]:
        artifact_id = new_id()
        run_root = (self.root / result.run_id).resolve()
        artifact_root = self.root.resolve()
        if not run_root.is_relative_to(artifact_root):
            raise ValueError("Artifact path escaped configured root")
        run_root.mkdir(parents=True, exist_ok=True)
        path = run_root / f"{artifact_id}.json"
        payload = result.model_dump_json(indent=2).encode("utf-8")
        path.write_bytes(payload)
        return artifact_id, path, hashlib.sha256(payload).hexdigest()

    def read_result(self, path: Path) -> AnalysisResult:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise ValueError("Artifact path escaped configured root")
        return AnalysisResult.model_validate_json(resolved.read_text(encoding="utf-8"))
