from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from urllib import error, parse, request

from .observability import log_event, record_counter, record_histogram, traced_operation


class JiraConfigurationError(RuntimeError):
    """Signal that the Jira adapter cannot start because env configuration is incomplete."""

    pass


class JiraClientError(RuntimeError):
    """Signal that a Jira REST operation failed or returned an unusable payload."""

    pass


@dataclass(frozen=True)
class JiraConfig:
    """Store the Jira connection and workflow settings used by the adapter."""

    base_url: str
    project_key: str
    email: str
    api_token: str
    issue_type: str = "Task"
    default_labels: tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: int = 15
    resolved_transition_name: str | None = None

    @classmethod
    def from_env(cls) -> "JiraConfig":
        """Build validated Jira settings from the repository root environment."""
        base_url = os.getenv("JIRA_BASE_URL", "").strip()
        project_key = os.getenv("JIRA_PROJECT_KEY", "").strip()
        email = os.getenv("ATLASSIAN_EMAIL", "").strip()
        api_token = os.getenv("ATLASSIAN_API_TOKEN", "").strip()

        missing = [
            name
            for name, value in (
                ("JIRA_BASE_URL", base_url),
                ("JIRA_PROJECT_KEY", project_key),
                ("ATLASSIAN_EMAIL", email),
                ("ATLASSIAN_API_TOKEN", api_token),
            )
            if not value
        ]
        if missing:
            missing_values = ", ".join(missing)
            raise JiraConfigurationError(f"Missing Jira configuration: {missing_values}")

        default_labels = tuple(
            label.strip()
            for label in os.getenv("JIRA_DEFAULT_LABELS", "sre,observability").split(",")
            if label.strip()
        )
        timeout_value = os.getenv("JIRA_TIMEOUT_SECONDS", "15").strip()

        return cls(
            base_url=base_url.rstrip("/"),
            project_key=project_key,
            email=email,
            api_token=api_token,
            issue_type=os.getenv("JIRA_ISSUE_TYPE", "Task").strip() or "Task",
            default_labels=default_labels,
            timeout_seconds=int(timeout_value or "15"),
            resolved_transition_name=_optional_env("JIRA_RESOLVED_TRANSITION_NAME"),
        )


@dataclass(frozen=True)
class JiraIssueReference:
    """Represent the Jira issue that was created through the adapter."""

    issue_key: str
    issue_url: str
    issue_id: str | None = None


class JiraClient:
    def __init__(self, config: JiraConfig):
        """Keep a configured Jira REST client ready for repeated operations."""
        self.config = config

    def create_issue(
        self,
        *,
        summary: str,
        description: dict[str, Any],
        labels: list[str],
        request_id: str,
    ) -> JiraIssueReference:
        """Create a new Jira issue with a summary, ADF description, and labels."""
        payload = {
            "fields": {
                "project": {"key": self.config.project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": self.config.issue_type},
                "labels": labels,
            }
        }
        response = self._request_json(
            method="POST",
            path="/rest/api/3/issue",
            payload=payload,
            request_id=request_id,
            operation="create_issue",
        )
        issue_key = response["key"]
        return JiraIssueReference(
            issue_key=issue_key,
            issue_url=self.issue_browse_url(issue_key),
            issue_id=response.get("id"),
        )

    def get_transitions(
        self,
        *,
        issue_key: str,
        request_id: str,
    ) -> list[dict[str, Any]]:
        """Fetch the workflow transitions Jira currently allows for the issue."""
        encoded_issue_key = parse.quote(issue_key, safe="")
        response = self._request_json(
            method="GET",
            path=f"/rest/api/3/issue/{encoded_issue_key}/transitions",
            request_id=request_id,
            operation="get_transitions",
        )
        return response.get("transitions", [])

    def transition_issue(
        self,
        *,
        issue_key: str,
        transition_id: str,
        request_id: str,
    ) -> None:
        """Move a Jira issue to a specific workflow transition by transition ID."""
        encoded_issue_key = parse.quote(issue_key, safe="")
        self._request_json(
            method="POST",
            path=f"/rest/api/3/issue/{encoded_issue_key}/transitions",
            payload={"transition": {"id": transition_id}},
            request_id=request_id,
            operation="transition_issue",
        )

    def issue_browse_url(self, issue_key: str) -> str:
        """Return the human-facing Jira browser URL for an issue key."""
        return f"{self.config.base_url}/browse/{issue_key}"

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        request_id: str,
        operation: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a Jira REST call with shared auth, logging, traces, and metrics."""
        url = f"{self.config.base_url}{path}"
        if query:
            url = f"{url}?{parse.urlencode(query, doseq=True)}"

        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(
            url=url,
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Basic {self._basic_auth_token()}",
            },
        )

        started_at = perf_counter()
        attributes = {"operation": operation, "http.method": method, "http.route": path}
        with traced_operation(f"jira.http.{operation}", request_id, **attributes):
            try:
                with request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                    raw_body = response.read().decode("utf-8")
                    duration_ms = (perf_counter() - started_at) * 1000
                    metric_attributes = {
                        "operation": operation,
                        "status_code": response.status,
                    }
                    record_counter("jira_http_requests_total", attributes=metric_attributes)
                    record_histogram(
                        "jira_http_request_duration_ms",
                        duration_ms,
                        attributes=metric_attributes,
                    )
                    log_event(
                        "info",
                        "jira.http.completed",
                        request_id,
                        operation=operation,
                        status_code=response.status,
                        duration_ms=round(duration_ms, 2),
                    )
                    return json.loads(raw_body) if raw_body else {}
            except error.HTTPError as exc:
                duration_ms = (perf_counter() - started_at) * 1000
                raw_body = exc.read().decode("utf-8", errors="replace")
                metric_attributes = {
                    "operation": operation,
                    "status_code": exc.code,
                }
                record_counter("jira_http_failures_total", attributes=metric_attributes)
                record_histogram(
                    "jira_http_request_duration_ms",
                    duration_ms,
                    attributes=metric_attributes,
                )
                log_event(
                    "error",
                    "jira.http.failed",
                    request_id,
                    operation=operation,
                    status_code=exc.code,
                    duration_ms=round(duration_ms, 2),
                    response_body=raw_body[:1200],
                )
                raise JiraClientError(
                    f"Jira {operation} failed with status {exc.code}: {raw_body[:200]}"
                ) from exc
            except error.URLError as exc:
                duration_ms = (perf_counter() - started_at) * 1000
                record_counter("jira_http_failures_total", attributes={"operation": operation})
                record_histogram(
                    "jira_http_request_duration_ms",
                    duration_ms,
                    attributes={"operation": operation},
                )
                log_event(
                    "error",
                    "jira.http.unreachable",
                    request_id,
                    operation=operation,
                    duration_ms=round(duration_ms, 2),
                    error=str(exc.reason),
                )
                raise JiraClientError(f"Jira {operation} failed: {exc.reason}") from exc

    def _basic_auth_token(self) -> str:
        """Encode Atlassian email plus API token as a Basic Auth credential."""
        credentials = f"{self.config.email}:{self.config.api_token}".encode("utf-8")
        return base64.b64encode(credentials).decode("ascii")


def _optional_env(name: str) -> str | None:
    """Read an optional environment variable without forcing empty strings downstream."""
    value = os.getenv(name, "").strip()
    return value or None
