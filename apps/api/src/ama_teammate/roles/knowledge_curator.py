from __future__ import annotations

from typing import Protocol


class KnowledgeCuratorRole(Protocol):
    def phase_context(self) -> str: ...


class PhaseOneKnowledgeCuratorMock:
    def phase_context(self) -> str:
        return (
            "No document parser or retrieval index is enabled. Never claim a document was read. "
            "Label retrieved facts Unknown and state that ingestion is postponed to Phase 3."
        )
