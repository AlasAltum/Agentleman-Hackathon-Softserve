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

### Atlassian Cloud API Token Setup

This adapter is documented for Atlassian Cloud. Atlassian's current basic-auth guidance for Cloud uses an Atlassian account email address plus an API token, not an account password.

1. Sign in to your Atlassian account and open `https://id.atlassian.com/manage-profile/security/api-tokens`.
2. Create a new API token for this integration and give it a clear name such as `agentleman-backend-jira`.
3. Copy the token when Atlassian shows it. Atlassian only shows the full token value at creation time.
4. Put your Atlassian account email in `ATLASSIAN_EMAIL`.
5. Put the new token in `ATLASSIAN_API_TOKEN`.
6. Set `JIRA_BASE_URL` to your Jira Cloud site, for example `https://your-company.atlassian.net`.
7. Set `JIRA_PROJECT_KEY` to the Jira project where the agent should create and resolve issues.
8. Make sure that Atlassian account can create issues and transition issues in that project.

Example root `.env` values:

```env
ATLASSIAN_EMAIL=engineer@example.com
ATLASSIAN_API_TOKEN=atlassian_api_token_here
JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_PROJECT_KEY=SRE
JIRA_ISSUE_TYPE=Task
JIRA_DEFAULT_LABELS=sre,observability
```

Do not commit real Atlassian credentials. Keep the real token only in the local runtime `.env` or in your deployment secret store.

### Behaviour

- New incidents create a new Jira issue.
- Triage data only affects Jira labels.
- The ticket summary and description come from the reported incident content, not from the agent's triage narrative.
- Resolution is a separate explicit flow that transitions the Jira issue without adding comments.

### Jira Resolution Webhook

When a human resolves a Jira task in the Jira UI, Jira should send an `issue updated` webhook to the backend. The backend route filters those events and only processes them when all of the following are true:

- the webhook event is `jira:issue_updated`
- the changelog includes a `status` change
- the actor is a human Atlassian user with `accountType = atlassian`
- the issue moved into a resolved state such as `Done`, `Resolved`, `Closed`, or any status category whose key is `done`

Backend endpoint:

```text
POST /api/webhook/jira/resolved
```

At runtime the webhook is projected into the internal `ResolutionPayload` and passed to the resolution phase. The webhook route then reuses the same ticketing notification fan-out used by the workflow so the reporter resolution email follows the same path in both environments.

For local development, when the backend cannot expose a public webhook endpoint, the workflow can start a per-ticket poller by setting `POLL_JIRA_TICKETS=true`. That poller checks Jira every 30 seconds and calls the same backend webhook route with a synthetic Jira payload once the issue reaches a resolved state.

Example Jira webhook body shape used by the backend:

```json
{
	"webhookEvent": "jira:issue_updated",
	"user": {
		"displayName": "Jane Ops",
		"accountType": "atlassian"
	},
	"issue": {
		"key": "SRE-123",
		"fields": {
			"summary": "Checkout API returns 500 after payment confirmation",
			"status": {
				"name": "Done",
				"statusCategory": {
					"key": "done"
				}
			}
		}
	},
	"changelog": {
		"items": [
			{
				"field": "status",
				"fromString": "In Progress",
				"toString": "Done"
			}
		]
	}
}
```

### Agent Tool Contract

The agent should call only the two public methods in `src.services.jira.bridge`.

The webhook below is different: Jira calls the HTTP endpoint, and the backend converts that incoming payload into the internal `ResolutionPayload` used by the resolution phase.


#### 1. Create Ticket

Signature:

```python
create_ticket(preprocessed: PreprocessedIncident, triage: TriageResult, request_id: str) -> TicketInfo
```

Required inputs:

- `preprocessed.original.text_desc`: original incident text that becomes the Jira summary and part of the description
- `preprocessed.original.reporter_email`: reporter identity stored in the Jira description and returned in `TicketInfo`
- `preprocessed.consolidated_text`: extra processed context for the Jira description
- `triage.classification.incident_type`: used for labels like `incident-new_incident`
- `triage.severity`: used for labels like `severity-high`
- `request_id`: required non-empty request identifier for logs, traces, and metrics

`TriageResult.technical_summary` and `TriageResult.business_impact_summary` are still required when constructing the model, even though the Jira adapter does not place those values into the Jira summary or description.

Minimal invocation:

```python
from src.services.jira.bridge import create_ticket
from src.workflow.models import (
	ClassificationResult,
	IncidentInput,
	IncidentType,
	PreprocessedIncident,
	Severity,
	TriageResult,
)

ticket = create_ticket(
	preprocessed=PreprocessedIncident(
		original=IncidentInput(
			text_desc="Checkout API returns 500 after payment confirmation",
			reporter_email="reporter@example.com",
		),
		consolidated_text="Checkout API returns 500 after payment confirmation in production.",
	),
	triage=TriageResult(
		classification=ClassificationResult(
			incident_type=IncidentType.NEW_INCIDENT,
			top_candidates=[],
		),
		tool_results=[],
		technical_summary="Checkout API p99 latency regressed after deployment.",
		severity=Severity.HIGH,
		business_impact_summary="Checkout completion rate is dropping.",
	),
	request_id="incident-2026-04-09-create",
)
```

Returned object:

```python
TicketInfo(
	ticket_id="SRE-123",
	ticket_url="https://your-company.atlassian.net/browse/SRE-123",
	action="created",
	reporter_email="reporter@example.com",
)
```

#### 2. Update Ticket State By Resolving It

Signature:

```python
resolve_ticket(payload: ResolutionPayload, request_id: str) -> JiraResolutionResult
```

Required inputs:

- `payload.ticket_id`: existing Jira issue key such as `SRE-123`
- `payload.resolved_by`: actor or service name performing the resolution
- `payload.resolution_notes`: resolution context for workflow logging
- `request_id`: required non-empty request identifier for logs, traces, and metrics

Minimal invocation:

```python
from src.services.jira.bridge import resolve_ticket
from src.workflow.models import ResolutionPayload

resolution = resolve_ticket(
	payload=ResolutionPayload(
		ticket_id="SRE-123",
		resolved_by="jira-live-test-runner",
		resolution_notes="Rollback completed and checkout recovered.",
	),
	request_id="incident-2026-04-09-resolve",
)
```

Returned object:

```python
JiraResolutionResult(
	ticket_id="SRE-123",
	ticket_url="https://your-company.atlassian.net/browse/SRE-123",
	transition_id="31",
	transition_name="Done",
	resolved_by="jira-live-test-runner",
)
```

If your Jira workflow uses a non-standard resolution transition name, set `JIRA_RESOLVED_TRANSITION_NAME` in the root `.env`.

#### 3. Receive Jira Resolution Webhook

HTTP contract:

```text
POST /api/webhook/jira/resolved
```

This is an inbound integration point. Jira should call this endpoint when a human transitions an issue into a resolved state. The backend then projects the webhook payload into the same `ResolutionPayload` model shown in the resolution flow.

Required webhook inputs:

- `webhookEvent`: should be `jira:issue_updated`
- `user.accountType`: should be `atlassian` so the backend knows a human triggered the resolution
- `user.displayName`: becomes `resolved_by` in the internal payload
- `issue.key`: becomes `ticket_id`
- `issue.fields.summary`: added to the generated `resolution_notes`
- `issue.fields.status.name` or `issue.fields.status.statusCategory.key`: must indicate a resolved state such as `Done`
- `changelog.items[]`: must contain an item whose `field` is `status`

Minimal invocation:

```bash
curl -X POST http://localhost:8000/api/webhook/jira/resolved \
	-H "Content-Type: application/json" \
	-d '{
		"webhookEvent": "jira:issue_updated",
		"user": {
			"displayName": "Jane Ops",
			"accountType": "atlassian"
		},
		"issue": {
			"key": "SRE-123",
			"fields": {
				"summary": "Checkout API returns 500 after payment confirmation",
				"status": {
					"name": "Done",
					"statusCategory": {
						"key": "done"
					}
				}
			}
		},
		"changelog": {
			"items": [
				{
					"field": "status",
					"fromString": "In Progress",
					"toString": "Done"
				}
			]
		}
	}'
```

Internal projected payload:

```python
ResolutionPayload(
		ticket_id="SRE-123",
		resolved_by="Jane Ops",
		resolution_notes="Jira webhook status transition: In Progress -> Done. Issue summary: Checkout API returns 500 after payment confirmation",
)
```

HTTP response when processed:

```json
{
	"status": "resolution_processed",
	"ticket_id": "SRE-123"
}
```

HTTP response when ignored:

```json
{
	"status": "ignored",
	"reason": "non_human_actor",
	"ticket_id": "SRE-123"
}
```

The webhook route does not call `resolve_ticket(...)`. It runs after Jira has already moved the issue to a resolved state.

### Observability

This adapter emits:

- JSON log events such as `jira.ticket.created.started`, `jira.ticket.created.completed`, `jira.ticket.resolution.completed`, and `jira.http.completed`
- spans such as `jira.create_ticket`, `jira.resolve_ticket`, and `jira.http.create_issue`
- counters and histograms such as `jira_tickets_created_total`, `jira_tickets_resolved_total`, and `jira_http_request_duration_ms`

### Validation

Run the service-local tests from the backend directory:

```bash
pytest src/services/jira/tests/test_bridge.py
```

Live Jira integration coverage lives in [backend/src/services/jira/tests/test_live_jira_integration.py](backend/src/services/jira/tests/test_live_jira_integration.py). One test intentionally leaves a created issue open so the team can inspect its state, and another creates then resolves an issue through the adapter.

To clean test issues afterwards, run [backend/src/services/jira/clean_test_issues.py](backend/src/services/jira/clean_test_issues.py). By default it deletes issues labeled `agentleman-jira-live-test`, and `--dry-run` lets you inspect the target set first.
 