## NYLAS Email Notification Service

This directory contains the email-only notification adapter used by the incident workflow.

### What It Does

- sends team notification emails through the NYLAS Email API
- sends reporter acknowledgement emails when a ticket is created
- exposes a reporter resolution email flow for future post-resolution wiring
- emits structured logs, spans, and metrics for notification operations

### Entry Points

Main functions in `bridge.py`:

```python
from src.services.notifications.bridge import (
    notify_reporter_resolution,
    notify_reporter_ticket_created,
    notify_team,
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