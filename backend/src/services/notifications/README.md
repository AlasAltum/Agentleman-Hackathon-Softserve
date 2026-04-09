## NYLAS Email Notification Service

This directory contains the email-only notification adapter used by the workflow.

It is useful to separate two levels of the flow:

1. The workflow and webhook decide when a notification should happen.
2. This service decides which email is sent to the team and which email is sent to the reporter.

### Where Emails Are Triggered From The Main Flow

#### 1. When a Jira ticket is created in the workflow

This happens in `backend/src/workflow/sre_workflow.py`:

```python
# ── Step 6: Ticket + Notification ────────────────────────────────────────

@step
async def create_ticket_and_notify(
    self, ctx: Context, ev: TriageCompleteEvent
) -> StopEvent:
    request_id = await ctx.store.get("request_id", default="unknown")
    log_phase_start("ticketing", component="workflow", request_id=request_id)
    reporter_email = ev.preprocessed.original.reporter_email
    ticket = await _create_new_ticket(ev.triage, reporter_email, ev.preprocessed)
    # Notify the team, besides the reporter
    dispatch_notifications(ticket, ev.triage, request_id)
    log_phase_success("ticketing", latency_ms=0, ticket_id=ticket.ticket_id, action=ticket.action, request_id=request_id)
    return StopEvent(result=ticket)
```

Important detail:

- `dispatch_notifications(ticket, ev.triage, request_id)` does not send only the team email.
- In the ticket-created path, it fans out into both:
  - the detailed email for the team
  - the high-level acknowledgement email for the reporter

That fan-out happens in `backend/src/workflow/phases/ticketing.py`:

```python
def dispatch_notifications(
    ticket: TicketInfo | None = None,
    triage: TriageResult | None = None,
    request_id: str = "unknown",
    *,
    resolution_payload: ResolutionPayload | None = None,
) -> None:
    if resolution_payload is not None:
        active_request_id = resolution_payload.request_id or request_id
        _send_resolution_reporter_email(resolution_payload, active_request_id)
        return

    if ticket is None or triage is None:
        raise ValueError("ticket and triage are required when resolution_payload is not provided")

    active_request_id = ticket.request_id or request_id
    _send_team_notifications(ticket, triage, active_request_id)
    _send_reporter_email(ticket, triage, active_request_id)
```

In this ticket-created branch:

- `_send_team_notifications(...)` sends the email to the engineering team.
- `_send_reporter_email(...)` sends the email to the reporter.

#### 2. When a Jira ticket is resolved through the webhook

This happens in `backend/src/api/routes/incident_routes.py`:

```python
@router.post("/webhook/jira/resolved")
@router.post("/webhook/resolved")
async def on_ticket_resolved(payload: dict[str, Any]):
    issue_key = _extract_issue_key(payload)
    ignore_reason = _jira_resolution_ignore_reason(payload)
    if ignore_reason is not None:
        return {
            "status": "ignored",
            "reason": ignore_reason,
            "ticket_id": issue_key,
        }

    resolution_payload = _build_resolution_payload(payload)
    handle_resolution(resolution_payload)
    dispatch_notifications(
        request_id=resolution_payload.request_id or "unknown",
        resolution_payload=resolution_payload,
    )
    return {"status": "resolution_processed", "ticket_id": resolution_payload.ticket_id}
```

In this resolution branch:

- `dispatch_notifications(..., resolution_payload=resolution_payload)` does not send a team email.
- It routes to `_send_resolution_reporter_email(...)`.
- That means the resolution webhook sends the reporter resolution email.

### Which Functions Send The Team Email

There are two relevant layers.

Workflow layer:

- `backend/src/workflow/phases/ticketing.py -> _send_team_notifications(...)`

Notification service layer:

- `bridge.py -> notify_team(ticket, triage, request_id=None)` (this is the notification-service-level function, distinct from the workflow-level `dispatch_notifications`)

This function sends the team email to all recipients in `NYLAS_TEAM_EMAIL_RECIPIENTS`.

The team email content is built in:

- `_team_email_subject(...)`
- `_team_email_body(...)`
- `_team_report_body(...)`

The actual NYLAS API call is done through:

- `_dispatch_email(...)`
- `client.py -> NylasClient.send_email(...)`

### Which Functions Send The Reporter Email

#### Reporter email when the ticket is created

Workflow layer:

- `backend/src/workflow/phases/ticketing.py -> _send_reporter_email(...)`

Notification service layer:

- `bridge.py -> notify_reporter_ticket_created(ticket, triage, request_id=None)`

The reporter ticket-created email content is built in:

- `_reporter_ticket_created_subject(...)`
- `_reporter_ticket_created_email_body(...)`

This email is intentionally high level.

#### Reporter email when the ticket is resolved

Workflow layer:

- `backend/src/workflow/phases/ticketing.py -> _send_resolution_reporter_email(...)`

Notification service layer:

- `bridge.py -> notify_reporter_resolution(reporter_email, payload, request_id=None)`

The reporter resolution email content is built in:

- `_reporter_resolution_subject(...)`
- `_reporter_resolution_email_body(...)`

### Current Content Split

The split is intentional:

- Team email: detailed, includes request id, Jira ticket, reporter email, severity, and the full report.
- Reporter ticket-created email: high level, short acknowledgement.
- Reporter resolution email: high level resolution update.

### Entry Points Inside This Service

Main public functions in `bridge.py`:

```python
from src.services.notifications.bridge import (
    notify_reporter_resolution,
    notify_reporter_ticket_created,
    dispatch_notifications,
)
```

### Environment Variables

Required:

- `NYLAS_API_KEY`
- `NYLAS_GRANT_ID`
- `NYLAS_EMAIL_ADDRESS`

Recommended:

- `NYLAS_TEAM_EMAIL_RECIPIENTS` comma-separated team email recipients

Optional:

- `NYLAS_EMAIL_REPLY_TO`
- `NYLAS_BASE_URL` default: `https://api.us.nylas.com/v3`
- `NYLAS_INCLUDE_TICKET_URL` default: `false`
- `NYLAS_TIMEOUT_SECONDS` default: `15`

The legacy typo `NYLAS_EMAIL_ADRESS` is also accepted at runtime for compatibility, but `NYLAS_EMAIL_ADDRESS` is the preferred variable name.

### Validation

Run the service-local tests from the backend directory:

```bash
pytest src/services/notifications/tests/test_bridge.py
```