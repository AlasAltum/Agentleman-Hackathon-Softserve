import asyncio
import uuid
from typing import Optional

from llama_index.core.llms import ChatMessage

from src.utils.logger import logger
from src.utils.setup import get_settings
from src.workflow.models import PreprocessedIncident, TicketInfo, TriageResult


_SUMMARY_PROMPT = """\
You are an SRE lead writing a Jira ticket for an incident. Given the investigation findings below, produce:

1. TITLE: A concise one-line title (max 80 chars). Format: [SEVERITY] Short description of root cause.
2. SUMMARY: 2-3 sentence executive summary of what happened, root cause, and immediate impact.
3. ROOT_CAUSE: One paragraph with the specific technical root cause.
4. IMPACT: One sentence on affected users/flows.
5. ACTION: Bullet list of 2-4 concrete remediation steps.

Severity: {severity}
Incident type: {incident_type}
Reporter: {reporter_email}

Original report:
{original_text}

Tool findings:
{tool_findings}

Respond with exactly these sections, each on a new line starting with the label (e.g. "TITLE: ...").
"""


async def _llm_summarize(triage: TriageResult, preprocessed: PreprocessedIncident) -> dict[str, str]:
    """Use the configured LLM to produce a condensed ticket summary. Falls back to raw data."""
    llm = get_settings().get("llm")
    if llm is None:
        return {}

    tool_findings = "\n\n".join(
        f"[{r.tool_name}]:\n{r.findings[:2000]}"  # cap per tool to avoid huge prompts
        for r in triage.tool_results
        if r.findings and not r.findings.startswith("Business impact") and not r.findings.startswith("Telemetry")
    ) or "No tool findings available."

    prompt = _SUMMARY_PROMPT.format(
        severity=triage.severity.value.upper(),
        incident_type=triage.classification.incident_type.value.replace("_", " ").title(),
        reporter_email=preprocessed.original.reporter_email,
        original_text=preprocessed.original.text_desc[:500],
        tool_findings=tool_findings,
    )

    try:
        messages = [ChatMessage(role="user", content=prompt)]
        response = await asyncio.to_thread(llm.chat, messages)
        text = response.message.content or ""
        result = {}
        for line in text.splitlines():
            for key in ("TITLE", "SUMMARY", "ROOT_CAUSE", "IMPACT", "ACTION"):
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
        logger.warning("ticket_llm_summarize_failed", error=str(exc))
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


def _build_ticket_description(
    triage: TriageResult,
    preprocessed: Optional[PreprocessedIncident] = None,
    llm_summary: dict[str, str] | None = None,
) -> str:
    """Build a structured Jira ticket description, using LLM summary when available."""
    severity = triage.severity.value.upper()
    incident_type = triage.classification.incident_type.value.replace("_", " ").title()

    if llm_summary and llm_summary.get("SUMMARY"):
        lines = [
            "h2. Incident Summary",
            llm_summary.get("SUMMARY", ""),
            "",
            f"*Severity:* {severity}",
            f"*Incident Type:* {incident_type}",
        ]
        if llm_summary.get("ROOT_CAUSE"):
            lines += ["", "h2. Root Cause", llm_summary["ROOT_CAUSE"]]
        if llm_summary.get("IMPACT"):
            lines += ["", "h2. Impact", llm_summary["IMPACT"]]
        if llm_summary.get("ACTION"):
            lines += ["", "h2. Recommended Actions", llm_summary["ACTION"]]
        lines += ["", "h2. Business Impact", triage.business_impact_summary]
    else:
        # Fallback: raw triage data
        lines = [
            "h2. Incident Summary",
            triage.technical_summary,
            "",
            f"*Severity:* {severity}",
            f"*Incident Type:* {incident_type}",
            "",
            "h2. Business Impact",
            triage.business_impact_summary,
        ]
        if triage.tool_results:
            lines += ["", "h2. Tool Findings"]
            for result in triage.tool_results:
                hint = f" (severity hint: {result.severity_hint.value})" if result.severity_hint else ""
                lines.append(f"*{result.tool_name}*{hint}: {result.findings}")

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

    title = _build_ticket_title(triage, llm_summary)
    description = _build_ticket_description(triage, preprocessed, llm_summary)
    logger.info("ticket_created", ticket_id=ticket_id, severity=triage.severity, title=title)

    if preprocessed and preprocessed.security_flag:
        logger.warning(
            "ticket_from_flagged_input",
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
    )



def _notify_team(ticket: TicketInfo, triage: TriageResult) -> None:
    """Notify technical team via Slack and Email."""
    logger.info(
        "team_notification",
        ticket_id=ticket.ticket_id,
        severity=triage.severity,
    )
    _send_slack_notification(ticket, triage)
    _send_team_email(ticket, triage)


def _send_slack_notification(ticket: TicketInfo, triage: TriageResult) -> None:
    """Stub: send Slack message to SRE channel until Slack integration is wired."""
    logger.info(
        "slack_notification",
        channel="#sre-alerts",
        ticket_id=ticket.ticket_id,
        severity=triage.severity,
    )


def _send_team_email(ticket: TicketInfo, triage: TriageResult) -> None:
    """Stub: send email to SRE team distribution list until email integration is wired."""
    logger.info(
        "email_notification",
        recipient="sre-team@company.com",
        ticket_id=ticket.ticket_id,
        severity=triage.severity,
    )