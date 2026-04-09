from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.workflow.models import (  # noqa: E402
    ClassificationResult,
    HistoricalCandidate,
    IncidentType,
    ResolutionPayload,
    Severity,
    TicketInfo,
    TriageResult,
)


def _module():
    return importlib.import_module("src.services.notifications.bridge")


def _triage_result() -> TriageResult:
    candidate = HistoricalCandidate(
        incident_id="INC-100",
        timestamp=datetime(2026, 4, 8, 10, 0, 0),
        description="Checkout failures and API latency",
        resolution="Scaled workers",
        similarity_score=0.91,
    )
    return TriageResult(
        classification=ClassificationResult(
            incident_type=IncidentType.NEW_INCIDENT,
            top_candidates=[candidate],
            historical_rca="Worker saturation",
        ),
        tool_results=[],
        technical_summary="API p99 latency regressed after deployment",
        severity=Severity.HIGH,
        business_impact_summary="Checkout completion rate is dropping.",
    )


def test_notify_team_sends_team_emails(monkeypatch):
    bridge = _module()
    captured: list[dict[str, str | None]] = []

    monkeypatch.setenv("NYLAS_API_KEY", "nyk_test")
    monkeypatch.setenv("NYLAS_GRANT_ID", "grant-123")
    monkeypatch.setenv("NYLAS_EMAIL_ADDRESS", "alerts@example.com")
    monkeypatch.setenv("NYLAS_TEAM_EMAIL_RECIPIENTS", "sre@example.com,helpdesk@example.com")

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def send_email(self, *, to, subject, body, request_id, reply_to=None):
            captured.append({"to": to, "subject": subject, "body": body, "reply_to": reply_to})
            return {"message_id": f"msg-{len(captured)}", "status": "sent"}

    monkeypatch.setattr(bridge, "NylasClient", FakeClient)

    result = bridge.notify_team(
        TicketInfo(
            ticket_id="SRE-100",
            ticket_url="https://example.atlassian.net/browse/SRE-100",
            action="created",
            reporter_email="reporter@example.com",
            description="Original report:\nCheckout API returns 500 after payment confirmation",
            request_id="req-100",
        ),
        _triage_result(),
    )

    assert len(result.dispatched) == 2
    assert not result.failed
    assert {item["to"] for item in captured} == {"sre@example.com", "helpdesk@example.com"}
    assert all(item["subject"] == "[HIGH] Incident report - req-100" for item in captured)
    assert all("Request ID: req-100" in (item["body"] or "") for item in captured)
    assert all("Full report:" in (item["body"] or "") for item in captured)
    assert all("Original report:" in (item["body"] or "") for item in captured)


def test_notify_reporter_ticket_created_sends_email_to_ticket_reporter(monkeypatch):
    bridge = _module()
    captured: list[dict[str, str | None]] = []

    monkeypatch.setenv("NYLAS_API_KEY", "nyk_test")
    monkeypatch.setenv("NYLAS_GRANT_ID", "grant-123")
    monkeypatch.setenv("NYLAS_EMAIL_ADDRESS", "alerts@example.com")

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def send_email(self, *, to, subject, body, request_id, reply_to=None):
            captured.append({"to": to, "subject": subject, "body": body, "request_id": request_id})
            return {"message_id": "msg-email", "status": "sent"}

    monkeypatch.setattr(bridge, "NylasClient", FakeClient)

    result = bridge.notify_reporter_ticket_created(
        TicketInfo(
            ticket_id="SRE-101",
            ticket_url="https://example.atlassian.net/browse/SRE-101",
            action="created",
            reporter_email="reporter@example.com",
            title="[HIGH] Checkout failures after deploy",
            request_id="req-101",
        ),
        _triage_result(),
        request_id="req-101",
    )

    assert len(result.dispatched) == 1
    assert not result.failed
    assert captured == [
        {
            "to": "reporter@example.com",
            "subject": "Ticket assigned - req-101",
            "body": "You have been assigned ticket #req-101.\nYou will be notified once this issue is resolved.\nThanks for reporting this issue.\nOur teams have already been notified.",
            "request_id": "req-101",
        }
    ]


def test_notify_reporter_resolution_sends_email(monkeypatch):
    bridge = _module()
    captured: list[dict[str, str | None]] = []

    monkeypatch.setenv("NYLAS_API_KEY", "nyk_test")
    monkeypatch.setenv("NYLAS_GRANT_ID", "grant-123")
    monkeypatch.setenv("NYLAS_EMAIL_ADDRESS", "alerts@example.com")

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def send_email(self, *, to, subject, body, request_id, reply_to=None):
            captured.append({"to": to, "subject": subject, "body": body, "request_id": request_id})
            return {"message_id": "msg-resolution", "status": "sent"}

    monkeypatch.setattr(bridge, "NylasClient", FakeClient)

    result = bridge.notify_reporter_resolution(
        reporter_email="reporter@example.com",
        payload=ResolutionPayload(
            ticket_id="SRE-200",
            resolved_by="ops@example.com",
            resolution_notes="Rolled back the deployment and restarted workers.",
            request_id="req-200",
        ),
        request_id="req-200",
    )

    assert len(result.dispatched) == 1
    assert not result.failed
    assert captured == [
        {
            "to": "reporter@example.com",
            "subject": "Issue resolved - req-200",
            "body": "Your reported issue #req-200 has been resolved.\nJira ticket: SRE-200\nResolved by: ops@example.com\nResolution notes: Rolled back the deployment and restarted workers.",
            "request_id": "req-200",
        }
    ]