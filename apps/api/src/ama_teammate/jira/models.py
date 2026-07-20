from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JiraUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    username: str | None = None


class JiraComment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    author: JiraUser | None = None
    body: str = Field(max_length=8_000)
    created: datetime | None = None
    updated: datetime | None = None


class JiraIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    project_key: str
    summary: str = Field(max_length=2_000)
    description: str = Field(default="", max_length=20_000)
    status: str
    issue_type: str
    priority: str | None = None
    assignee: JiraUser | None = None
    reporter: JiraUser | None = None
    labels: list[str] = Field(default_factory=list, max_length=100)
    components: list[str] = Field(default_factory=list, max_length=100)
    fix_versions: list[str] = Field(default_factory=list, max_length=100)
    resolution: str | None = None
    created: datetime | None = None
    updated: datetime | None = None
    comments: list[JiraComment] = Field(default_factory=list)
    source_url: str


class JiraHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    configured: bool
    available: bool
    authenticated_user: str | None = None
    error_code: str | None = None


class JiraActionPlan(BaseModel):
    """Validated, reviewable Jira action produced before any connector call."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["read", "search", "create", "transition", "clarify"]
    issue_key: str | None = Field(default=None, max_length=64)
    project_key: str | None = Field(default=None, max_length=32)
    jql: str | None = Field(default=None, max_length=2_000)
    max_results: int = Field(default=25, ge=1, le=50)
    summary: str | None = Field(default=None, max_length=2_000)
    description: str | None = Field(default=None, max_length=20_000)
    issue_type: str | None = Field(default=None, max_length=200)
    priority: str | None = Field(default=None, max_length=200)
    target_status: str | None = Field(default=None, max_length=200)
    clarification_question: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_action_fields(self) -> JiraActionPlan:
        required: dict[str, tuple[str, ...]] = {
            "read": ("issue_key",),
            "search": ("jql",),
            "create": ("project_key", "summary", "issue_type"),
            "transition": ("issue_key", "target_status"),
            "clarify": ("clarification_question",),
        }
        missing = [name for name in required[self.action] if not getattr(self, name)]
        if missing:
            raise ValueError(f"{self.action} requires: {', '.join(missing)}")
        return self

    @property
    def requires_approval(self) -> bool:
        return self.action in {"create", "transition"}

    def approval_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"clarification_question"})
