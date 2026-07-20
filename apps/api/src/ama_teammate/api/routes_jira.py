from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ama_teammate.api.dependencies import DevelopmentUser, get_current_user
from ama_teammate.errors import AppError
from ama_teammate.jira.client import JiraConnectorError
from ama_teammate.jira.models import JiraHealth, JiraIssue
from ama_teammate.jira.service import JiraReadService

router = APIRouter(prefix="/integrations/jira", tags=["jira"])


def _service(request: Request) -> JiraReadService:
    return request.app.state.jira_service  # type: ignore[no-any-return]


@router.get("/health")
async def jira_health(
    request: Request, user: DevelopmentUser = Depends(get_current_user)
) -> JiraHealth:
    del user
    return await _service(request).health()


@router.get("/issues/{issue_key}")
async def get_jira_issue(
    issue_key: str,
    request: Request,
    user: DevelopmentUser = Depends(get_current_user),
) -> JiraIssue:
    try:
        issue = await _service(request).get_issue(issue_key)
    except JiraConnectorError as exc:
        await request.app.state.repository.add_audit_event(
            actor_id=user.id,
            event_type="jira.issue.read",
            status="failed",
            safe_details={"issue_key": issue_key.upper(), "result": exc.code},
        )
        raise AppError(
            status_code=exc.status_code,
            code=exc.code,
            category="external_service",
            message="The Jira issue could not be read.",
            recovery="Check the issue key, project allowlist, Jira access, and connector health.",
        ) from exc
    await request.app.state.repository.add_audit_event(
        actor_id=user.id,
        event_type="jira.issue.read",
        status="success",
        safe_details={"issue_key": issue.key, "project_key": issue.project_key},
    )
    return issue
