from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QueryProposal(BaseModel):
    id: str
    source_id: str
    sql: str
    parameters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    purpose: str
    max_rows: int
    max_result_bytes: int
    timeout_seconds: float


class ValidatedQuery(BaseModel):
    proposal_id: str
    source_id: str
    dialect: str
    normalized_sql: str
    executable_sql: str
    parameters: dict[str, str | int | float | bool | None]
    referenced_tables: list[str]
    referenced_columns: list[str]
    max_rows: int
    max_result_bytes: int
    timeout_seconds: float
    policy_version: str

    def approval_payload(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "source_id": self.source_id,
            "dialect": self.dialect,
            "normalized_sql": self.normalized_sql,
            "parameters": self.parameters,
            "max_rows": self.max_rows,
            "max_result_bytes": self.max_result_bytes,
            "timeout_seconds": self.timeout_seconds,
            "policy_version": self.policy_version,
        }


class SQLPolicyViolation(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
