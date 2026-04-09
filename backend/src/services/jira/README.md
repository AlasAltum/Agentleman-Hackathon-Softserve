## Jira Service Adapter

This directory contains an isolated Jira adapter for the triage workflow.

### What It Does

- creates Jira issues for new incidents
- moves Jira issues to their resolved state through a dedicated resolution flow
- emits structured JSON logs for each operation
- creates OTEL spans and metrics when `opentelemetry` is available in the runtime

### Entry Point

The public flows are in `bridge.py`:

```python
from src.services.jira.bridge import create_ticket, resolve_ticket
```

If you want to keep the current folder name strategy for the ZAVU service, the matching future workflow hook can use `importlib.import_module(...)` for both services.

### Environment Variables

Required:

- `ATLASSIAN_EMAIL`
- `ATLASSIAN_API_TOKEN`
- `JIRA_BASE_URL`
- `JIRA_PROJECT_KEY`

Optional:

- `JIRA_ISSUE_TYPE` default: `Task`
- `JIRA_DEFAULT_LABELS` default: `sre,observability`
- `JIRA_TIMEOUT_SECONDS` default: `15`
- `JIRA_RESOLVED_TRANSITION_NAME` if your Jira workflow does not use a standard name such as `Done` or `Resolved`

These variables should live in the repository root `.env.example` and runtime `.env`.

### Behaviour

- New incidents create a new Jira issue.
- Triage data only affects Jira labels.
- The ticket summary and description come from the reported incident content, not from the agent's triage narrative.
- Resolution is a separate explicit flow that transitions the Jira issue without adding comments.

### Observability

This adapter emits:

- JSON log events such as `jira.ticketing.created` and `jira.http.completed`
- spans such as `jira.create_ticket`, `jira.resolve_ticket`, and `jira.http.create_issue`
- counters and histograms such as `jira_tickets_created_total`, `jira_tickets_resolved_total`, and `jira_http_request_duration_ms`

### Validation

Run the service-local tests from the backend directory:

```bash
pytest src/services/jira/tests/test_bridge.py
```
 