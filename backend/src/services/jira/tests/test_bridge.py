from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[4]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.workflow.models import (  # noqa: E402
    ClassificationResult,
    IncidentInput,
    HistoricalCandidate,
    IncidentType,
    PreprocessedIncident,
    ResolutionPayload,
    Severity,
    TriageResult,
)


def _module():
    return importlib.import_module("src.services.jira.bridge")


def _preprocessed_incident(security_flag: str | None = None) -> PreprocessedIncident:
    return PreprocessedIncident(
        original=IncidentInput(
            text_desc="Checkout API returns 500 after payment confirmation",
            reporter_email="reporter@example.com",
        ),
        consolidated_text="Checkout API returns 500 after payment confirmation in the production checkout flow.",
        security_flag=security_flag,
        request_id="req-123",
    )


def _triage_result(incident_type: IncidentType, incident_id: str = "INC-100") -> TriageResult:
    candidate = HistoricalCandidate(
        incident_id=incident_id,
        timestamp=datetime(2026, 4, 8, 10, 0, 0),
        description="Checkout failures and API latency",
        resolution="Scaled workers",
        similarity_score=0.91,
    )
    return TriageResult(
        classification=ClassificationResult(
            incident_type=incident_type,
            top_candidates=[candidate],
            historical_rca="Worker saturation",
        ),
        tool_results=[],
        technical_summary="API p99 latency regressed after deployment",
        severity=Severity.HIGH,
        business_impact_summary="Checkout completion rate is dropping.",
    )


def test_create_ticket_creates_new_issue(monkeypatch):
    bridge = _module()
    captured: dict[str, object] = {}

    monkeypatch.setenv("ATLASSIAN_EMAIL", "alerts@example.com")
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token")
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "SRE")

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def create_issue(self, *, summary, description, labels, request_id):
            captured["summary"] = summary
            captured["description"] = description
            captured["labels"] = labels
            captured["request_id"] = request_id
            client_module = importlib.import_module("src.services.jira.client")
            return client_module.JiraIssueReference(
                issue_key="SRE-123",
                issue_url="https://example.atlassian.net/browse/SRE-123",
                issue_id="10001",
            )

        def issue_browse_url(self, issue_key):
            return f"https://example.atlassian.net/browse/{issue_key}"

    monkeypatch.setattr(bridge, "JiraClient", FakeClient)

    result = bridge.create_ticket(
        _preprocessed_incident(security_flag="prompt-injection-review"),
        _triage_result(IncidentType.NEW_INCIDENT),
        request_id="req-123",
    )

    assert result.ticket_id == "SRE-123"
    assert result.action == "created"
    assert result.reporter_email == "reporter@example.com"
    assert result.request_id == "req-123"
    assert captured["summary"] == "Incident report - Checkout API returns 500 after payment confirmation"
    labels = cast(list[str], captured["labels"])
    assert "incident-new_incident" in labels
    assert "severity-high" in labels
    assert "security-review" in labels
    description_text = str(captured["description"])
    assert "Request ID: req-123" in description_text
    assert "Original report:" in description_text
    assert "Technical summary:" not in description_text


def test_create_ticket_requires_request_id(monkeypatch):
    bridge = _module()

    monkeypatch.setenv("ATLASSIAN_EMAIL", "alerts@example.com")
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token")
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "SRE")

    class FakeClient:
        def __init__(self, config):
            self.config = config

    monkeypatch.setattr(bridge, "JiraClient", FakeClient)

    with pytest.raises(ValueError, match="request_id is required"):
        bridge.create_ticket(
            _preprocessed_incident(),
            _triage_result(IncidentType.NEW_INCIDENT),
            request_id="   ",
        )


def test_resolve_ticket_transitions_issue(monkeypatch):
    bridge = _module()
    captured: dict[str, object] = {}

    monkeypatch.setenv("ATLASSIAN_EMAIL", "alerts@example.com")
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token")
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "SRE")
    monkeypatch.setenv("JIRA_RESOLVED_TRANSITION_NAME", "Done")

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def get_transitions(self, *, issue_key, request_id):
            captured["issue_key"] = issue_key
            return [
                {"id": "11", "name": "In Progress"},
                {"id": "31", "name": "Done"},
            ]

        def transition_issue(self, *, issue_key, transition_id, request_id):
            captured["transition_issue_key"] = issue_key
            captured["transition_id"] = transition_id

        def issue_browse_url(self, issue_key):
            return f"https://example.atlassian.net/browse/{issue_key}"

    monkeypatch.setattr(bridge, "JiraClient", FakeClient)

    result = bridge.resolve_ticket(
        ResolutionPayload(
            ticket_id="SRE-77",
            resolved_by="ops@example.com",
            resolution_notes="Rollback completed successfully.",
        ),
        request_id="req-resolve",
    )

    assert result.ticket_id == "SRE-77"
    assert result.transition_id == "31"
    assert result.transition_name == "Done"
    assert captured["transition_issue_key"] == "SRE-77"
    assert captured["transition_id"] == "31"


@pytest.mark.asyncio
async def test_poll_ticket_until_resolved_calls_resolution_webhook(monkeypatch):
    bridge = _module()
    captured: dict[str, object] = {}

    monkeypatch.setenv("ATLASSIAN_EMAIL", "alerts@example.com")
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "token")
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "SRE")

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def get_issue(self, *, issue_key, fields, request_id):
            captured["issue_key"] = issue_key
            captured["fields"] = fields
            captured["request_id"] = request_id
            return {
                "key": issue_key,
                "fields": {
                    "summary": "Checkout API returns 500 after payment confirmation",
                    "status": {
                        "name": "Done",
                        "statusCategory": {"key": "done"},
                    },
                    "description": {
                        "version": 1,
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "Reporter email: reporter@example.com"}
                                ],
                            },
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "Request ID: req-123"}
                                ],
                            },
                        ],
                    },
                },
            }

    async def _fake_on_ticket_resolved(payload):
        captured["payload"] = payload
        return {"status": "resolution_processed"}

    monkeypatch.setattr(bridge, "JiraClient", FakeClient)

    incident_routes = importlib.import_module("src.api.routes.incident_routes")
    monkeypatch.setattr(incident_routes, "on_ticket_resolved", _fake_on_ticket_resolved)

    await bridge.poll_ticket_until_resolved(
        ticket=bridge.TicketInfo(
            ticket_id="SRE-123",
            ticket_url="https://example.atlassian.net/browse/SRE-123",
            action="created",
            reporter_email="reporter@example.com",
            request_id="req-123",
        ),
        request_id="req-123",
        poll_interval_seconds=0,
    )

    assert captured["issue_key"] == "SRE-123"
    assert captured["fields"] == ["summary", "status", "description"]
    webhook_payload = cast(dict[str, object], captured["payload"])
    assert webhook_payload["webhookEvent"] == "jira:issue_updated"
    assert cast(dict[str, object], webhook_payload["issue"])["key"] == "SRE-123"