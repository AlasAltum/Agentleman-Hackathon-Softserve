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
    return importlib.import_module("src.services.notification-zavu.bridge")


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


def test_notify_team_sends_email_and_telegram(monkeypatch):
    bridge = _module()
    captured: list[dict[str, str | None]] = []

    monkeypatch.setenv("ZAVU_API_KEY", "zv_test")
    monkeypatch.setenv("ZAVU_TEAM_EMAIL_RECIPIENTS", "sre@example.com")
    monkeypatch.setenv("ZAVU_TEAM_TELEGRAM_CHAT_IDS", "123456")

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def send_message(
            self,
            *,
            to,
            channel,
            text,
            request_id,
            subject=None,
            html_body=None,
            reply_to=None,
            idempotency_key=None,
        ):
            captured.append(
                {
                    "to": to,
                    "channel": channel,
                    "subject": subject,
                    "idempotency_key": idempotency_key,
                }
            )
            return {"message": {"id": f"msg-{channel}", "status": "queued"}}

    monkeypatch.setattr(bridge, "ZavuClient", FakeClient)

    result = bridge.notify_team(
        TicketInfo(
            ticket_id="SRE-100",
            ticket_url="https://example.atlassian.net/browse/SRE-100",
            action="created",
            reporter_email="reporter@example.com",
        ),
        _triage_result(),
    )

    assert len(result.dispatched) == 2
    assert not result.failed
    assert {item["channel"] for item in captured} == {"email", "telegram"}


def test_notify_reporter_resolution_uses_optional_telegram_mapping(monkeypatch):
    bridge = _module()
    captured: list[dict[str, str | None]] = []

    monkeypatch.setenv("ZAVU_API_KEY", "zv_test")
    monkeypatch.setenv("ZAVU_REPORTER_TELEGRAM_MAP", '{"reporter@example.com": "999"}')

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def send_message(
            self,
            *,
            to,
            channel,
            text,
            request_id,
            subject=None,
            html_body=None,
            reply_to=None,
            idempotency_key=None,
        ):
            captured.append({"to": to, "channel": channel, "subject": subject})
            return {"messageId": f"msg-{channel}", "status": "accepted"}

    monkeypatch.setattr(bridge, "ZavuClient", FakeClient)

    result = bridge.notify_reporter_resolution(
        reporter_email="reporter@example.com",
        payload=ResolutionPayload(
            ticket_id="SRE-200",
            resolved_by="ops@example.com",
            resolution_notes="Rolled back the deployment and restarted workers.",
        ),
    )

    assert len(result.dispatched) == 2
    assert {item["channel"] for item in captured} == {"email", "telegram"}