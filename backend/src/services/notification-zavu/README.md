## ZAVU Notification Adapter

This directory contains an isolated ZAVU adapter for team notifications and reporter resolution messages.

### What It Does

- sends email notifications through the ZAVU API
- sends Telegram notifications through the same API
- fans out to multiple configured recipients
- emits structured JSON logs for each operation
- creates OTEL spans and metrics when `opentelemetry` is available in the runtime

### Entry Points

Main functions in `bridge.py`:

```python
import importlib

zavu = importlib.import_module("src.services.notification-zavu.bridge")
team_result = zavu.notify_team(ticket, triage)
reporter_result = zavu.notify_reporter_resolution(reporter_email, payload)
```

`importlib` is used here because the directory name intentionally contains a hyphen.

### Environment Variables

Required:

- `ZAVU_API_KEY`

Recommended:

- `ZAVU_TEAM_EMAIL_RECIPIENTS` comma-separated team emails
- `ZAVU_TEAM_TELEGRAM_CHAT_IDS` comma-separated Telegram chat IDs

Optional:

- `ZAVU_BASE_URL` default: `https://api.zavu.dev`
- `ZAVU_EMAIL_REPLY_TO`
- `ZAVU_SENDER_ID`
- `ZAVU_INCLUDE_TICKET_URL` default: `false`
- `ZAVU_REPORTER_TELEGRAM_MAP` JSON object mapping reporter email to Telegram chat ID
- `ZAVU_TIMEOUT_SECONDS` default: `15`

See `.env.example` in this folder for a service-local template.

### ZAVU Caveats From The Docs

- Email sending requires KYC verification in ZAVU.
- Telegram outbound requires a valid chat ID.
- URLs in email content can require prior URL verification in ZAVU, so this adapter keeps ticket links disabled by default.

### Observability

This adapter emits:

- JSON log events such as `zavu.message.sent` and `zavu.http.completed`
- spans such as `zavu.notify_team` and `zavu.http.send_email`
- counters and histograms such as `zavu_notifications_sent_total` and `zavu_http_request_duration_ms`

### Validation

Run the service-local tests from the backend directory:

```bash
pytest src/services/notification-zavu/tests/test_bridge.py
```
