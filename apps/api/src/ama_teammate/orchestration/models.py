from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GoalAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: Literal["chat", "analysis", "knowledge"]
    task_goal: str = Field(min_length=1, max_length=500)
    missing_fields: list[str] = Field(default_factory=list, max_length=4)
    decision_summary: str = Field(min_length=1, max_length=500)
    confidence: float = Field(default=0.8, ge=0, le=1)
