from __future__ import annotations

from typing import Protocol


class DataAnalystRole(Protocol):
    def phase_context(self) -> str: ...


class PhaseOneDataAnalystMock:
    def phase_context(self) -> str:
        return (
            "No database connector is enabled. Never claim a query ran or invent rows. "
            "Label analytical results Unknown and state that execution is postponed to Phase 2."
        )
