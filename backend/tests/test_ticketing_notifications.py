from types import SimpleNamespace
from unittest.mock import Mock

from src.workflow.models import ClassificationResult, IncidentType, Severity, TicketInfo, TriageResult
from src.workflow.phases import ticketing


def _triage_result() -> TriageResult:
    return TriageResult(
        classification=ClassificationResult(incident_type=IncidentType.NEW_INCIDENT),
        tool_results=[],
        technical_summary="Checkout latency regressed after the latest deployment.",
        severity=Severity.HIGH,
        business_impact_summary="Checkout conversion is dropping.",
    )


def test_notify_team_also_sends_reporter_email(monkeypatch):
    fake_bridge = Mock()
    fake_bridge.notify_team.return_value = SimpleNamespace(dispatched=[object()], failed=[])
    fake_bridge.notify_reporter_ticket_created.return_value = SimpleNamespace(dispatched=[object()], failed=[])
    start_resolution_poller = Mock()

    def _fake_import_module(name: str):
        assert name == "src.services.notifications.bridge"
        return fake_bridge

    monkeypatch.setattr(ticketing.importlib, "import_module", _fake_import_module)
    monkeypatch.setattr(ticketing, "_start_resolution_poller", start_resolution_poller)

    ticket = TicketInfo(
        ticket_id="SRE-900",
        ticket_url="https://jira.example.com/browse/SRE-900",
        reporter_email="reporter@example.com",
        action="created",
        title="[HIGH] Checkout degraded",
        request_id="req-123",
    )
    triage = _triage_result()

    ticketing.dispatch_notifications(ticket, triage, request_id="req-123")

    fake_bridge.notify_team.assert_called_once_with(ticket, triage, request_id="req-123")
    fake_bridge.notify_reporter_ticket_created.assert_called_once_with(
        ticket,
        triage,
        request_id="req-123",
    )
    start_resolution_poller.assert_called_once_with(ticket, "req-123")


def test_notify_team_routes_resolution_notifications_through_bridge(monkeypatch):
    fake_bridge = Mock()
    fake_bridge.notify_reporter_resolution.return_value = SimpleNamespace(
        dispatched=[object()],
        failed=[],
    )

    def _fake_import_module(name: str):
        assert name == "src.services.notifications.bridge"
        return fake_bridge

    monkeypatch.setattr(ticketing.importlib, "import_module", _fake_import_module)

    payload = ticketing.ResolutionPayload(
        ticket_id="SRE-901",
        resolved_by="Jane Ops",
        resolution_notes="Rollback completed successfully.",
        reporter_email="reporter@example.com",
        request_id="req-901",
    )

    ticketing.dispatch_notifications(request_id="fallback-id", resolution_payload=payload)

    fake_bridge.notify_reporter_resolution.assert_called_once_with(
        "reporter@example.com",
        payload,
        request_id="req-901",
    )