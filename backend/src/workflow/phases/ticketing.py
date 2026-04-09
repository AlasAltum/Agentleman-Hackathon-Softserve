import importlib
import asyncio
import os
import uuid
from typing import Optional

from llama_index.core.llms import ChatMessage

from src.utils.logger import logger
from src.utils.setup import get_settings
from src.workflow.models import PreprocessedIncident, ResolutionPayload, TicketInfo, TriageResult

_NOTIFICATION_BRIDGE_MODULE = "src.services.notifications.bridge"
_JIRA_BRIDGE_MODULE = "src.services.jira.bridge"
_LOCAL_RESOLUTION_POLL_INTERVAL_SECONDS = 45
_RESOLUTION_POLLER_TASKS: set[asyncio.Task[None]] = set()


_SUMMARY_PROMPT = """\
You are a senior SRE lead writing a Jira incident ticket. Your audience is both the engineering \
team (who need technical precision) and engineering management (who need to understand business \
consequences quickly).

Given the investigation findings below, produce the following sections:

1. TITLE: One-line title (max 80 chars). Format: [SEVERITY] Short description of root cause.

2. SUMMARY: 2-3 sentences covering what happened, the technical root cause, and the \
   business-level consequence (e.g. revenue loss, users affected, SLA risk). \
   Lead with the business impact if it is significant.

3. ROOT_CAUSE: One paragraph with the specific technical root cause. Be precise: name the \
   service, metric, error, or code path that caused the failure.

4. IMPACT: Two parts on separate lines:
   - Technical: affected services, error rates, latency figures.
   - Business: estimated revenue loss, users affected, Customer Impact Score, and any SLA \
     breach risk. Pull exact figures from the business_impact findings if available.

5. ACTION: Bullet list of 3-5 concrete remediation steps ordered by priority. \
   Include at least one step addressing the business risk (e.g. "Notify customer success \
   team if outage exceeded X minutes").

6. BUSINESS_RISK: One sentence summarising the financial exposure and whether it warrants \
   immediate escalation to management. Use the estimated dollar figures from business_impact \
   if present.

Rules:
- Always include BUSINESS_RISK even if the financial figures are estimates.
- If business_impact findings show CRITICAL severity, start SUMMARY with "⚠ HIGH BUSINESS IMPACT:".
- If incident type is "Alert Storm", the ticket is a NEW ticket (not an update). \
  Reflect in SUMMARY that this is a recurring alert still active, and in ACTION \
  include a step to suppress or deduplicate downstream alerts.
- Respond with exactly these section labels, each starting a new line (e.g. "TITLE: ...").

---
Severity: {severity}
Incident type: {incident_type}
Reporter: {reporter_email}

Original report:
{original_text}

Tool findings:
{tool_findings}
"""


async def _llm_summarize(triage: TriageResult, preprocessed: PreprocessedIncident) -> dict[str, str]:
    """Use the configured LLM to produce a condensed ticket summary. Falls back to raw data."""
    llm = get_settings().get("llm")
    if llm is None:
        return {}

    tool_findings = "\n\n".join(
        f"[{r.tool_name}]:\n{r.findings[:2000]}"
        for r in triage.tool_results
        if r.findings
    ) or "No tool findings available."

    prompt = _SUMMARY_PROMPT.format(
        severity=triage.severity.value.upper(),
        incident_type=triage.classification.incident_type.value.replace("_", " ").title(),
        reporter_email=preprocessed.original.reporter_email,
        original_text=preprocessed.original.text_desc[:500],
        tool_findings=tool_findings,
    )

    request_id = preprocessed.request_id or "unknown"
    try:
        messages = [ChatMessage(role="user", content=prompt)]
        response = await asyncio.to_thread(llm.chat, messages)
        text = response.message.content or ""
        result = {}
        for line in text.splitlines():
            for key in ("TITLE", "SUMMARY", "ROOT_CAUSE", "IMPACT", "ACTION", "BUSINESS_RISK"):
                if line.startswith(f"{key}:"):
                    result[key] = line[len(key) + 1:].strip()
                    break
            else:
                # Multi-line values: append to last key
                if result:
                    last_key = list(result)[-1]
                    result[last_key] += "\n" + line
        return result
    except Exception as exc:
        logger.warning("ticket_llm_summarize_failed", request_id=request_id, error=str(exc))
        return {}



def _build_ticket_title(triage: TriageResult, llm_summary: dict[str, str] | None = None) -> str:
    """Derive a concise ticket title from the LLM summary or triage result."""
    severity = triage.severity.value.upper()
    if llm_summary and llm_summary.get("TITLE"):
        title = llm_summary["TITLE"]
        # Strip leading [SEVERITY] if LLM already included it, we'll re-add consistently
        if title.startswith("["):
            return title[:120]
        return f"[{severity}] {title[:110]}"
    incident_type = triage.classification.incident_type.value.replace("_", " ").title()
    first_sentence = triage.technical_summary.split(".")[0].strip()
    if len(first_sentence) > 80:
        first_sentence = first_sentence[:77] + "..."
    return f"[{severity}] {incident_type}: {first_sentence}"


def _metadata_lines(
    severity: str,
    incident_type: str,
    preprocessed: Optional[PreprocessedIncident],
) -> list[str]:
    lines = [f"*Severity:* {severity}", f"*Incident Type:* {incident_type}"]
    if preprocessed and preprocessed.request_id:
        lines.append(f"*Request ID:* {preprocessed.request_id}")
    return lines


def _description_from_llm(
    triage: TriageResult,
    preprocessed: Optional[PreprocessedIncident],
    llm_summary: dict[str, str],
    severity: str,
    incident_type: str,
) -> list[str]:
    lines = ["h2. Incident Summary", llm_summary["SUMMARY"], ""]
    lines += _metadata_lines(severity, incident_type, preprocessed)
    for section_key, heading in (
        ("ROOT_CAUSE", "Root Cause"),
        ("IMPACT", "Impact"),
        ("ACTION", "Recommended Actions"),
        ("BUSINESS_RISK", "Business Risk"),
    ):
        if llm_summary.get(section_key):
            lines += ["", f"h2. {heading}", llm_summary[section_key]]
    lines += ["", "h2. Business Impact Detail", triage.business_impact_summary]
    return lines


def _description_fallback(
    triage: TriageResult,
    preprocessed: Optional[PreprocessedIncident],
    severity: str,
    incident_type: str,
) -> list[str]:
    lines = ["h2. Incident Summary", triage.technical_summary, ""]
    lines += _metadata_lines(severity, incident_type, preprocessed)
    lines += ["", "h2. Business Impact", triage.business_impact_summary]
    if triage.tool_results:
        lines += ["", "h2. Tool Findings"]
        for result in triage.tool_results:
            hint = f" (severity hint: {result.severity_hint.value})" if result.severity_hint else ""
            lines.append(f"*{result.tool_name}*{hint}: {result.findings}")
    return lines


def _build_ticket_description(
    triage: TriageResult,
    preprocessed: Optional[PreprocessedIncident] = None,
    llm_summary: dict[str, str] | None = None,
) -> str:
    """Build a structured Jira ticket description, using LLM summary when available."""
    severity = triage.severity.value.upper()
    incident_type = triage.classification.incident_type.value.replace("_", " ").title()

    if llm_summary and llm_summary.get("SUMMARY"):
        lines = _description_from_llm(triage, preprocessed, llm_summary, severity, incident_type)
    else:
        lines = _description_fallback(triage, preprocessed, severity, incident_type)

    if triage.classification.historical_rca:
        lines += ["", "h2. Historical RCA", triage.classification.historical_rca]
    if preprocessed:
        lines += ["", "h2. Original Report", preprocessed.original.text_desc]

    return "\n".join(lines)


async def _create_new_ticket(
    triage: TriageResult,
    reporter_email: str,
    preprocessed: Optional[PreprocessedIncident] = None,
) -> TicketInfo:
    """Create a new Jira ticket with an LLM-condensed summary.

    Stub: logs intent and returns mock ticket until Jira integration is wired.
    """
    ticket_id = f"SRE-{str(uuid.uuid4())[:8].upper()}"
    ticket_url = f"https://jira.example.com/browse/{ticket_id}"

    llm_summary = {}
    if preprocessed:
        llm_summary = await _llm_summarize(triage, preprocessed)

    request_id = preprocessed.request_id if preprocessed else "unknown"
    title = _build_ticket_title(triage, llm_summary)
    description = _build_ticket_description(triage, preprocessed, llm_summary)

    if preprocessed and _jira_ticketing_enabled():
        jira_bridge = _load_jira_bridge()
        jira_ticket = await asyncio.to_thread(
            jira_bridge.create_ticket,
            preprocessed,
            triage,
            request_id,
        )
        logger.info(
            "ticket_created",
            request_id=request_id,
            ticket_id=jira_ticket.ticket_id,
            severity=triage.severity,
            title=title,
            provider="jira",
        )
        return TicketInfo(
            ticket_id=jira_ticket.ticket_id,
            ticket_url=jira_ticket.ticket_url,
            action=jira_ticket.action,
            reporter_email=jira_ticket.reporter_email,
            title=title,
            description=description,
            request_id=jira_ticket.request_id or request_id,
        )

    logger.info("ticket_created", request_id=request_id, ticket_id=ticket_id, severity=triage.severity, title=title)

    if preprocessed and preprocessed.security_flag:
        logger.warning(
            "ticket_from_flagged_input",
            request_id=request_id,
            ticket_id=ticket_id,
            security_flag=preprocessed.security_flag,
        )
    return TicketInfo(
        ticket_id=ticket_id,
        ticket_url=ticket_url,
        action="created",
        reporter_email=reporter_email,
        title=title,
        description=description,
        request_id=request_id,
    )



def dispatch_notifications(
    ticket: TicketInfo | None = None,
    triage: TriageResult | None = None,
    request_id: str = "unknown",
    *,
    resolution_payload: ResolutionPayload | None = None,
) -> None:
    """Dispatch notification fan-out for ticket creation and resolution events to the 
    engineering team."""
    if resolution_payload is not None:
        active_request_id = resolution_payload.request_id or request_id
        logger.info(
            "resolution_notification",
            request_id=active_request_id,
            ticket_id=resolution_payload.ticket_id,
        )
        _send_resolution_reporter_email(resolution_payload, active_request_id)
        return

    if ticket is None or triage is None:
        raise ValueError("ticket and triage are required when resolution_payload is not provided")

    active_request_id = ticket.request_id or request_id
    logger.info(
        "team_notification",
        request_id=active_request_id,
        ticket_id=ticket.ticket_id,
        severity=triage.severity,
    )
    _send_team_notifications(ticket, triage, active_request_id)
    _send_reporter_email(ticket, triage, active_request_id)
    _start_resolution_poller(ticket, active_request_id)


def _load_notification_bridge():
    return importlib.import_module(_NOTIFICATION_BRIDGE_MODULE)


def _load_jira_bridge():
    return importlib.import_module(_JIRA_BRIDGE_MODULE)


def _jira_ticketing_enabled() -> bool:
    return all(
        os.getenv(name, "").strip()
        for name in (
            "JIRA_BASE_URL",
            "JIRA_PROJECT_KEY",
            "ATLASSIAN_EMAIL",
            "ATLASSIAN_API_TOKEN",
        )
    )


def _jira_polling_enabled() -> bool:
    value = os.getenv("POLL_JIRA_TICKETS", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _start_resolution_poller(ticket: TicketInfo, request_id: str) -> None:
    if not _jira_polling_enabled():
        return

    if not _jira_ticketing_enabled():
        return

    jira_bridge = _load_jira_bridge()
    task = asyncio.create_task(
        jira_bridge.poll_ticket_until_resolved(
            ticket,
            request_id=request_id,
            poll_interval_seconds=_LOCAL_RESOLUTION_POLL_INTERVAL_SECONDS,
        )
    )
    _RESOLUTION_POLLER_TASKS.add(task)
    task.add_done_callback(_RESOLUTION_POLLER_TASKS.discard)

def _send_team_notifications(ticket: TicketInfo, triage: TriageResult, request_id: str = "unknown") -> None:
    try:
        bridge = _load_notification_bridge()
        result = bridge.notify_team(ticket, triage, request_id=request_id)
    except Exception as exc:
        logger.warning(
            "team_notification_failed",
            request_id=request_id,
            ticket_id=ticket.ticket_id,
            error=str(exc),
        )
        return

    logger.info(
        "team_notification_dispatched",
        request_id=request_id,
        ticket_id=ticket.ticket_id,
        severity=triage.severity,
        dispatched=len(result.dispatched),
        failed=len(result.failed),
    )


def _send_reporter_email(ticket: TicketInfo, triage: TriageResult, request_id: str = "unknown") -> None:
    reporter_email = ticket.reporter_email.strip()
    if not reporter_email:
        logger.warning(
            "reporter_notification_skipped",
            request_id=request_id,
            ticket_id=ticket.ticket_id,
            reason="missing_reporter_email",
        )
        return

    try:
        bridge = _load_notification_bridge()
        result = bridge.notify_reporter_ticket_created(ticket, triage, request_id=request_id)
    except Exception as exc:
        logger.warning(
            "reporter_notification_failed",
            request_id=request_id,
            ticket_id=ticket.ticket_id,
            reporter_email=reporter_email,
            error=str(exc),
        )
        return

    logger.info(
        "reporter_notification_dispatched",
        request_id=request_id,
        ticket_id=ticket.ticket_id,
        reporter_email=reporter_email,
        severity=triage.severity,
        dispatched=len(result.dispatched),
        failed=len(result.failed),
    )


def _send_resolution_reporter_email(
    payload: ResolutionPayload,
    request_id: str = "unknown",
) -> None:
    reporter_email = (payload.reporter_email or "").strip()
    if not reporter_email:
        logger.info(
            "resolution_notification_skipped",
            request_id=request_id,
            ticket_id=payload.ticket_id,
            reason="missing_reporter_email",
        )
        return

    try:
        bridge = _load_notification_bridge()
        result = bridge.notify_reporter_resolution(
            reporter_email,
            payload,
            request_id=request_id,
        )
    except Exception as exc:
        logger.warning(
            "resolution_notification_failed",
            request_id=request_id,
            ticket_id=payload.ticket_id,
            reporter_email=reporter_email,
            error=str(exc),
        )
        return

    logger.info(
        "resolution_notification_dispatched",
        request_id=request_id,
        ticket_id=payload.ticket_id,
        reporter_email=reporter_email,
        dispatched=len(result.dispatched),
        failed=len(result.failed),
    )
