from __future__ import annotations

import asyncio
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from ama_teammate.jira.credentials import JiraCredentialError, JiraTokenProvider
from ama_teammate.jira.models import JiraComment, JiraHealth, JiraIssue, JiraUser


class JiraConnectorError(RuntimeError):
    def __init__(self, code: str, status_code: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class JiraTransport(Protocol):
    async def get_json(
        self, path: str, *, query: Mapping[str, str], headers: Mapping[str, str]
    ) -> dict[str, Any]: ...

    async def post_json(
        self, path: str, *, body: Mapping[str, Any], headers: Mapping[str, str]
    ) -> dict[str, Any]: ...


class UrllibJiraTransport:
    """Bounded Jira transport with environment proxies disabled for internal Jira."""

    def __init__(self, base_url: str, timeout_seconds: float, max_response_bytes: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        context = ssl.create_default_context()
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context)
        )

    async def get_json(
        self, path: str, *, query: Mapping[str, str], headers: Mapping[str, str]
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._request_json, "GET", path, query, headers, None)

    async def post_json(
        self, path: str, *, body: Mapping[str, Any], headers: Mapping[str, str]
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._request_json, "POST", path, {}, headers, body)

    def _request_json(
        self,
        method: str,
        path: str,
        query: Mapping[str, str],
        headers: Mapping[str, str],
        body: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers = dict(headers)
        if data is not None:
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, headers=request_headers, data=data, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read(self.max_response_bytes + 1)
        except urllib.error.HTTPError as exc:
            code = {
                400: "jira_bad_request",
                401: "jira_unauthorized",
                403: "jira_forbidden",
                404: "jira_not_found",
                409: "jira_conflict",
                429: "jira_rate_limited",
            }.get(exc.code, "jira_http_error")
            raise JiraConnectorError(code, exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise JiraConnectorError("jira_unavailable") from exc
        if len(raw) > self.max_response_bytes:
            raise JiraConnectorError("jira_response_too_large")
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JiraConnectorError("jira_invalid_response") from exc
        if not isinstance(payload, dict):
            raise JiraConnectorError("jira_invalid_response")
        return payload


class JiraReadOnlyClient:
    """Allowlisted Jira client; writes are separately disabled by default and approval-gated."""

    CORE_FIELDS = (
        "summary,description,status,issuetype,priority,assignee,reporter,labels,components,"
        "created,updated,resolution,fixVersions"
    )

    def __init__(
        self,
        *,
        base_url: str,
        allowed_projects: frozenset[str],
        token_provider: JiraTokenProvider,
        transport: JiraTransport,
        enabled: bool,
        comment_limit: int,
        write_enabled: bool = False,
        search_max_results: int = 50,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.allowed_projects = frozenset(item.upper() for item in allowed_projects)
        self.token_provider = token_provider
        self.transport = transport
        self.enabled = enabled
        self.comment_limit = comment_limit
        self.write_enabled = write_enabled
        self.search_max_results = min(max(search_max_results, 1), 50)

    async def health(self) -> JiraHealth:
        if not self.enabled:
            return JiraHealth(
                enabled=False, configured=False, available=False, error_code="disabled"
            )
        try:
            payload = await self._get("/rest/api/2/myself")
        except JiraCredentialError as exc:
            return JiraHealth(enabled=True, configured=False, available=False, error_code=str(exc))
        except JiraConnectorError as exc:
            credential_error = exc.code.startswith("jira_token_") or exc.code == (
                "jira_dpapi_unavailable"
            )
            return JiraHealth(
                enabled=True,
                configured=not credential_error,
                available=False,
                error_code=exc.code,
            )
        return JiraHealth(
            enabled=True,
            configured=True,
            available=True,
            authenticated_user=str(payload.get("displayName") or payload.get("name") or ""),
        )

    async def get_issue(self, issue_key: str) -> JiraIssue:
        key = issue_key.strip().upper()
        project_key = self._validate_issue_key(key)
        payload = await self._get(
            f"/rest/api/2/issue/{urllib.parse.quote(key, safe='-')}",
            {"fields": self.CORE_FIELDS},
        )
        comments_payload = await self._get(
            f"/rest/api/2/issue/{urllib.parse.quote(key, safe='-')}/comment",
            {"startAt": "0", "maxResults": str(self.comment_limit), "orderBy": "-created"},
        )
        comments = [
            _comment(item)
            for item in list(comments_payload.get("comments") or [])[: self.comment_limit]
            if isinstance(item, dict)
        ]
        return self._issue(payload, key=key, project_key=project_key, comments=comments)

    async def search_issues(self, jql: str, max_results: int = 25) -> list[JiraIssue]:
        safe_jql = self._scope_jql(jql)
        bounded = min(max(max_results, 1), self.search_max_results)
        payload = await self._get(
            "/rest/api/2/search",
            {
                "jql": safe_jql,
                "startAt": "0",
                "maxResults": str(bounded),
                "fields": self.CORE_FIELDS,
            },
        )
        issues: list[JiraIssue] = []
        for item in list(payload.get("issues") or [])[:bounded]:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").upper()
            project_key = self._validate_issue_key(key)
            issues.append(self._issue(item, key=key, project_key=project_key, comments=[]))
        return issues

    async def create_issue(
        self,
        *,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str,
        priority: str | None,
    ) -> JiraIssue:
        self._require_write_enabled()
        project = self._validate_project(project_key)
        fields: dict[str, Any] = {
            "project": {"key": project},
            "summary": summary.strip(),
            "description": description.strip(),
            "issuetype": {"name": issue_type.strip()},
        }
        if priority:
            fields["priority"] = {"name": priority.strip()}
        payload = await self._post("/rest/api/2/issue", {"fields": fields})
        key = str(payload.get("key") or "").upper()
        self._validate_issue_key(key)
        return await self.get_issue(key)

    async def transition_issue(self, issue_key: str, target_status: str) -> JiraIssue:
        self._require_write_enabled()
        key = issue_key.strip().upper()
        self._validate_issue_key(key)
        payload = await self._get(
            f"/rest/api/2/issue/{urllib.parse.quote(key, safe='-')}/transitions",
            {"expand": "transitions.fields"},
        )
        target = _normalize_name(target_status)
        matches = [
            item
            for item in list(payload.get("transitions") or [])
            if isinstance(item, dict) and _normalize_name(str(item.get("name") or "")) == target
        ]
        if len(matches) != 1:
            raise JiraConnectorError("jira_transition_not_available", 409)
        transition_id = str(matches[0].get("id") or "")
        if not transition_id:
            raise JiraConnectorError("jira_transition_not_available", 409)
        await self._post(
            f"/rest/api/2/issue/{urllib.parse.quote(key, safe='-')}/transitions",
            {"transition": {"id": transition_id}},
        )
        return await self.get_issue(key)

    async def _get(self, path: str, query: Mapping[str, str] | None = None) -> dict[str, Any]:
        headers = self._auth_headers()
        return await self.transport.get_json(path, query=query or {}, headers=headers)

    async def _post(self, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        headers = self._auth_headers()
        return await self.transport.post_json(path, body=body, headers=headers)

    def _auth_headers(self) -> dict[str, str]:
        if not self.enabled:
            raise JiraConnectorError("jira_disabled")
        try:
            token = self.token_provider.get_token()
        except JiraCredentialError as exc:
            raise JiraConnectorError(str(exc)) from exc
        return {"Accept": "application/json", "Authorization": f"Bearer {token}"}

    def _require_write_enabled(self) -> None:
        if not self.write_enabled:
            raise JiraConnectorError("jira_writes_disabled", 403)

    def _validate_issue_key(self, key: str) -> str:
        parts = key.split("-", 1)
        if len(parts) != 2 or not parts[0].isalnum() or not parts[1].isdigit():
            raise JiraConnectorError("jira_issue_key_invalid", 400)
        return self._validate_project(parts[0])

    def _validate_project(self, project_key: str) -> str:
        project = project_key.strip().upper()
        if not project or not project.isalnum():
            raise JiraConnectorError("jira_project_invalid", 400)
        if project not in self.allowed_projects:
            raise JiraConnectorError("jira_project_not_allowed", 403)
        return project

    def _scope_jql(self, jql: str) -> str:
        normalized = " ".join(jql.strip().split())
        if not normalized or len(normalized) > 2_000 or "\x00" in normalized:
            raise JiraConnectorError("jira_jql_invalid", 400)
        order_match = re.search(r"\s+ORDER\s+BY\s+.+$", normalized, re.IGNORECASE)
        order_clause = order_match.group(0).strip() if order_match else "ORDER BY updated DESC"
        predicate = normalized[: order_match.start()].strip() if order_match else normalized
        projects = ", ".join(f'"{item}"' for item in sorted(self.allowed_projects))
        return f"project in ({projects}) AND ({predicate}) {order_clause}"

    def _issue(
        self,
        payload: Mapping[str, Any],
        *,
        key: str,
        project_key: str,
        comments: list[JiraComment],
    ) -> JiraIssue:
        fields = _mapping(payload.get("fields"))
        return JiraIssue(
            key=key,
            project_key=project_key,
            summary=str(fields.get("summary") or "")[:2_000],
            description=_plain_text(fields.get("description"))[:20_000],
            status=_name(fields.get("status")),
            issue_type=_name(fields.get("issuetype")),
            priority=_optional_name(fields.get("priority")),
            assignee=_user(fields.get("assignee")),
            reporter=_user(fields.get("reporter")),
            labels=[str(item)[:200] for item in list(fields.get("labels") or [])[:100]],
            components=_names(fields.get("components")),
            fix_versions=_names(fields.get("fixVersions")),
            resolution=_optional_name(fields.get("resolution")),
            created=_datetime(fields.get("created")),
            updated=_datetime(fields.get("updated")),
            comments=comments,
            source_url=f"{self.base_url}/browse/{key}",
        )


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _name(value: Any) -> str:
    return str(_mapping(value).get("name") or "Unknown")[:500]


def _normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _optional_name(value: Any) -> str | None:
    result = _name(value)
    return None if result == "Unknown" else result


def _names(value: Any) -> list[str]:
    return [_name(item) for item in list(value or [])[:100]]


def _user(value: Any) -> JiraUser | None:
    item = _mapping(value)
    if not item:
        return None
    return JiraUser(
        display_name=str(item.get("displayName") or item.get("name") or "Unknown")[:500],
        username=str(item.get("name") or item.get("key") or "")[:500] or None,
    )


def _datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _plain_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(filter(None, (_plain_text(item) for item in value)))
    if isinstance(value, dict):
        parts: list[str] = []
        if isinstance(value.get("text"), str):
            parts.append(value["text"])
        if "content" in value:
            parts.append(_plain_text(value["content"]))
        return "\n".join(filter(None, parts))
    return ""


def _comment(value: dict[str, Any]) -> JiraComment:
    return JiraComment(
        id=str(value.get("id") or "")[:200],
        author=_user(value.get("author")),
        body=_plain_text(value.get("body"))[:8_000],
        created=_datetime(value.get("created")),
        updated=_datetime(value.get("updated")),
    )
