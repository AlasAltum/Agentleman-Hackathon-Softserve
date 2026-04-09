from __future__ import annotations

from datetime import datetime
from pathlib import Path
from time import monotonic, sleep

import pytest

from src.services.jira.bridge import create_ticket, resolve_ticket
from src.services.jira.client import JiraClient, JiraClientError, JiraConfig
from src.workflow.models import (
    ClassificationResult,
    HistoricalCandidate,
    IncidentInput,
    IncidentType,
    PreprocessedIncident,
    ResolutionPayload,
    Severity,
    TriageResult,
)

pytestmark = pytest.mark.integration

TEST_LABEL = "agentleman-jira-live-test"
OPEN_STATE_LABEL = "agentleman-jira-open-state"
RESOLVED_STATE_LABEL = "agentleman-jira-resolved-state"


def _load_root_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load the repository root `.env` into the test process for live Jira calls."""
    env_path = Path(__file__).resolve().parents[5] / ".env"
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        monkeypatch.setenv(key.strip(), value.strip().strip('"').strip("'"))


def _preprocessed_incident(scenario_name: str) -> PreprocessedIncident:
    """Build a realistic incident payload for a named live Jira scenario."""
    return PreprocessedIncident(
        original=IncidentInput(
            text_desc=f"[{scenario_name}] Checkout API returns 500 after payment confirmation",
            reporter_email="jira-live-tests@example.com",
            file_name="incident.log",
            file_mime_type="text/plain",
        ),
        consolidated_text=(
            f"[{scenario_name}] Checkout API returns 500 after payment confirmation in the production checkout flow."
        ),
        security_flag=None,
    )


def _triage_result() -> TriageResult:
    """Provide a stable triage payload so live Jira labels remain reproducible."""
    candidate = HistoricalCandidate(
        incident_id="INC-LIVE-001",
        timestamp=datetime(2026, 4, 9, 10, 0, 0),
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


def _jira_client() -> JiraClient:
    """Create a live Jira client from the root environment configuration."""
    return JiraClient(JiraConfig.from_env())


def _issue_status_category_key(issue_payload: dict) -> str:
    """Extract the Jira status category key used to distinguish open versus done states."""
    return (
        issue_payload.get("fields", {})
        .get("status", {})
        .get("statusCategory", {})
        .get("key", "")
        .lower()
    )


def _wait_until_issue_can_transition(issue_key: str, timeout_seconds: float = 10.0) -> None:
    """Poll Jira until a freshly created issue is available for workflow transitions."""
    client = _jira_client()
    deadline = monotonic() + timeout_seconds
    last_error: JiraClientError | None = None

    while monotonic() < deadline:
        try:
            transitions = client.get_transitions(
                issue_key=issue_key,
                request_id=f"live-jira-transition-wait-{issue_key}",
            )
        except JiraClientError as exc:
            last_error = exc
            sleep(1)
            continue

        if transitions:
            return
        sleep(1)

    if last_error is not None:
        raise last_error
    raise AssertionError(f"Jira issue {issue_key} never exposed workflow transitions.")


def test_live_jira_create_ticket_leaves_issue_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Create a real Jira issue and intentionally leave it unresolved for manual inspection."""
    _load_root_env(monkeypatch)
    monkeypatch.setenv(
        "JIRA_DEFAULT_LABELS",
        f"sre,observability,{TEST_LABEL},{OPEN_STATE_LABEL}",
    )

    ticket = create_ticket(
        _preprocessed_incident("live-open-state"),
        _triage_result(),
        request_id="live-jira-open-state",
    )
    issue_payload = _jira_client().get_issue(
        issue_key=ticket.ticket_id,
        fields=["summary", "labels", "status"],
        request_id="live-jira-open-state-check",
    )

    labels = issue_payload.get("fields", {}).get("labels", [])
    assert issue_payload["key"] == ticket.ticket_id
    assert TEST_LABEL in labels
    assert OPEN_STATE_LABEL in labels
    assert _issue_status_category_key(issue_payload) != "done"
    print(f"Left open Jira issue for inspection: {ticket.ticket_id}")


def test_live_jira_create_and_resolve_ticket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Create a real Jira issue, resolve it through the adapter, and confirm the final state."""
    _load_root_env(monkeypatch)
    monkeypatch.setenv(
        "JIRA_DEFAULT_LABELS",
        f"sre,observability,{TEST_LABEL},{RESOLVED_STATE_LABEL}",
    )

    ticket = create_ticket(
        _preprocessed_incident("live-resolved-state"),
        _triage_result(),
        request_id="live-jira-resolved-create",
    )
    _wait_until_issue_can_transition(ticket.ticket_id)
    resolution = resolve_ticket(
        ResolutionPayload(
            ticket_id=ticket.ticket_id,
            resolved_by="jira-live-test-runner",
            resolution_notes="Integration test resolution path.",
        ),
        request_id="live-jira-resolved-transition",
    )
    issue_payload = _jira_client().get_issue(
        issue_key=ticket.ticket_id,
        fields=["summary", "labels", "status"],
        request_id="live-jira-resolved-check",
    )

    labels = issue_payload.get("fields", {}).get("labels", [])
    assert resolution.ticket_id == ticket.ticket_id
    assert TEST_LABEL in labels
    assert RESOLVED_STATE_LABEL in labels
    assert _issue_status_category_key(issue_payload) == "done"
    print(f"Resolved Jira issue through live adapter: {ticket.ticket_id}")