"""Codebase analyzer tool — agentic loop that uses bash commands to find incident root causes.

The agent iteratively runs grep/find/cat commands guided by the LLM until it has enough
evidence to produce a structured diagnosis. Max 5 iterations.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
from pathlib import Path
from typing import Optional

from llama_index.core.llms import ChatMessage

from src.utils.setup import get_settings

from src.utils.logger import logger
from src.workflow.models import Severity, ToolResult

# ── Constants ─────────────────────────────────────────────────────────────────

ECOMMERCE_ROOT = os.getenv(
    "ECOMMERCE_ROOT",
    str(Path(__file__).resolve().parents[5] / "ecommerce-platform"),
)
MAX_ITERATIONS = 5
MAX_CMD_OUTPUT = 3000   # chars per command output before truncation
MAX_COMMANDS_PER_ITER = 4
BASH_TIMEOUT = 10.0     # seconds per bash command

_ALLOWED_CMDS = {"grep", "find", "head", "cat", "ls"}
_NO_OUTPUT = "[no output]"

_SEVERITY_MAP: dict[str, Severity] = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
}

# ── Public entry point ────────────────────────────────────────────────────────


TOOL_TIMEOUT = 90.0  # seconds — must stay well below the workflow-level timeout


async def analyze_codebase(incident_text: str) -> ToolResult:
    """Scan e-commerce codebase for errors, regressions, or relevant code paths.

    Uses an agentic loop: the LLM generates bash commands, results are fed back,
    and the loop repeats until the LLM declares it has enough evidence (max 5 iters).
    """
    logger.info("tool_execution", tool="codebase_analyzer", status="started")
    try:
        return await asyncio.wait_for(
            _run_agentic_analysis(incident_text), timeout=TOOL_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.warning(
            "tool_execution",
            tool="codebase_analyzer",
            status="timeout",
            timeout_s=TOOL_TIMEOUT,
        )
        return ToolResult(
            tool_name="codebase_analyzer",
            findings="Codebase analysis timed out — no findings within the time budget.",
            severity_hint=None,
        )
    except Exception as exc:
        logger.error(
            "tool_execution",
            tool="codebase_analyzer",
            status="failed",
            error=str(exc),
        )
        return ToolResult(
            tool_name="codebase_analyzer",
            findings=f"Codebase analysis failed: {type(exc).__name__}: {exc}",
            severity_hint=None,
        )


# ── Core agentic loop ─────────────────────────────────────────────────────────


async def _run_agentic_analysis(incident_text: str) -> ToolResult:
    if not Path(ECOMMERCE_ROOT).exists():
        logger.warning("codebase_analyzer_root_missing", path=ECOMMERCE_ROOT)
        return ToolResult(
            tool_name="codebase_analyzer",
            findings=(
                f"Ecommerce platform not found at: {ECOMMERCE_ROOT}. "
                "Skipping codebase analysis."
            ),
            severity_hint=None,
        )

    llm = _get_llm()
    if llm is None:
        logger.warning("codebase_analyzer_no_llm")
        return await _fallback_no_llm(incident_text)

    history: list[dict] = []

    # Boot: LLM generates first commands based on incident
    boot_prompt = _build_boot_prompt(incident_text)
    response_text = await _llm_call(llm, boot_prompt)
    parsed = _parse_agent_json(response_text)

    for iteration in range(MAX_ITERATIONS):
        commands = parsed.get("commands", [])[:MAX_COMMANDS_PER_ITER]
        done = parsed.get("done", False)
        reasoning = parsed.get("reasoning", "")

        # Execute all commands concurrently
        results = await asyncio.gather(*[_run_bash(cmd) for cmd in commands])

        iter_record = {
            "reasoning": reasoning,
            "commands": commands,
            "results": list(results),
        }
        history.append(iter_record)

        logger.info(
            "codebase_analyzer_iteration",
            iteration=iteration + 1,
            num_commands=len(commands),
            done=done,
        )

        if done or iteration == MAX_ITERATIONS - 1:
            break

        # Next iteration: LLM decides what to look at next
        iter_prompt = _build_iteration_prompt(incident_text, history)
        response_text = await _llm_call(llm, iter_prompt)
        parsed = _parse_agent_json(response_text)

    # Final report
    final_prompt = _build_final_prompt(incident_text, history)
    final_report = await _llm_call(llm, final_prompt)
    severity = _parse_severity(final_report)
    findings = _format_findings(history, final_report)

    logger.info(
        "tool_execution",
        tool="codebase_analyzer",
        status="completed",
        iterations=len(history),
        severity=severity,
    )
    return ToolResult(
        tool_name="codebase_analyzer",
        findings=findings,
        severity_hint=severity,
    )


# ── LLM helpers ───────────────────────────────────────────────────────────────


def _get_llm():
    """Return the globally configured LLM, or instantiate GoogleGenAI as fallback."""
    configured_llm = get_settings().get("llm")
    if configured_llm is not None:
        return configured_llm

    api_key = (
        os.getenv("GOOGLE_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("LLM_API_KEY")
    )
    if not api_key:
        return None

    try:
        from llama_index.llms.google_genai import GoogleGenAI  # type: ignore

        model = os.getenv("LLM_MODEL", "gemini-2.5-flash")
        return GoogleGenAI(model=model, api_key=api_key)
    except ImportError:
        logger.warning("codebase_analyzer_llm_import_failed", package="llama_index.llms.google_genai")
        return None


async def _llm_call(llm, prompt: str) -> str:
    """Call the LLM asynchronously (LlamaIndex LLMs are sync — wrap with to_thread)."""
    messages = [ChatMessage(role="user", content=prompt)]
    try:
        response = await asyncio.to_thread(llm.chat, messages)
        return response.message.content or ""
    except Exception as exc:
        logger.warning("codebase_analyzer_llm_call_failed", error=str(exc))
        return ""


# ── Bash execution ────────────────────────────────────────────────────────────


def _is_safe_command(cmd: str) -> bool:
    """Only allow a safe subset of read-only commands."""
    try:
        parts = shlex.split(cmd)
        return bool(parts) and parts[0] in _ALLOWED_CMDS
    except Exception:
        return False


async def _run_bash(cmd: str) -> str:
    """Execute a bash command safely and return stdout."""
    if not _is_safe_command(cmd):
        first = cmd.split()[0] if cmd.strip() else "?"
        logger.warning("codebase_analyzer_blocked_command", cmd=first)
        return f"[command not allowed: {first}]"

    try:
        args = shlex.split(cmd)
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=ECOMMERCE_ROOT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=BASH_TIMEOUT)
        result = stdout.decode("utf-8", errors="replace")
        if len(result) > MAX_CMD_OUTPUT:
            result = result[:MAX_CMD_OUTPUT] + f"\n... [truncated, {len(result)} total chars]"
        return result or _NO_OUTPUT
    except asyncio.TimeoutError:
        proc.kill()
        return "[command timed out]"
    except Exception as exc:
        return f"[command failed: {exc}]"


# ── Prompt builders ───────────────────────────────────────────────────────────

_BOOT_PROMPT = """\
You are an SRE agent analyzing a TypeScript e-commerce codebase for the root cause of an incident.

Codebase structure (working directory is ecommerce-platform/):
- api/src/   → Medusa.js backend (routes, modules, workflows, subscribers)
- web/src/   → Next.js 15 storefront (app/, modules/)

INCIDENT REPORT:
{incident_text}

Your job: generate bash commands to locate the relevant code.
Allowed commands: grep, find, head, cat, ls

Respond ONLY with valid JSON (no markdown fences):
{{"reasoning": "why you chose these commands", "commands": ["grep -rn 'payment' api/src/ --include='*.ts'"], "done": false}}

Rules:
- Max {max_cmds} commands per response
- Use grep -rn for content search, find for file discovery, cat/head to read files
- Set done=true only when you have enough evidence to diagnose the root cause
- IMPORTANT: Use ONLY relative paths from ecommerce-platform/. Never use absolute paths like /app/... or /home/... even if they appear in the incident report — those are production container paths, not local paths.
"""

_ITER_PROMPT = """\
You are an SRE agent investigating an incident iteratively.

INCIDENT: {incident_text}

INVESTIGATION SO FAR:
{history_text}

Based on what you found, what should you look at next?
Respond ONLY with valid JSON (no markdown fences):
{{"reasoning": "what you found and what to check next", "commands": ["..."], "done": false}}

Set done=true if you have enough evidence to diagnose the root cause.
Allowed commands: grep, find, head, cat, ls
Max {max_cmds} commands.
IMPORTANT: Use ONLY relative paths from ecommerce-platform/. Never use absolute paths like /app/... even if they appear in the incident — those are production container paths.
"""

_FINAL_PROMPT = """\
You are an SRE analyst. Write a final incident report based on your codebase investigation.

INCIDENT: {incident_text}

FULL INVESTIGATION:
{history_text}

Write a structured report with these sections:
1. ROOT CAUSE: specific file, function, or configuration causing the issue
2. EXPLANATION: what the bug or misconfiguration is and why it causes the incident
3. AFFECTED PATHS: which user flows or API endpoints are broken
4. RECOMMENDED ACTION: concrete fix or mitigation steps

End your response with EXACTLY this line (required):
SEVERITY: [CRITICAL|HIGH|MEDIUM|LOW]

Severity guide:
- CRITICAL: payment broken, data loss, all users affected
- HIGH: significant user-facing errors, checkout blocked for some users
- MEDIUM: partial or intermittent failures, non-critical paths affected
- LOW: minor issues, cosmetic errors, dev-only problems
"""


def _build_boot_prompt(incident_text: str) -> str:
    return _BOOT_PROMPT.format(
        incident_text=incident_text,
        max_cmds=MAX_COMMANDS_PER_ITER,
    )


def _build_iteration_prompt(incident_text: str, history: list[dict]) -> str:
    return _ITER_PROMPT.format(
        incident_text=incident_text,
        history_text=_format_history(history),
        max_cmds=MAX_COMMANDS_PER_ITER,
    )


def _build_final_prompt(incident_text: str, history: list[dict]) -> str:
    return _FINAL_PROMPT.format(
        incident_text=incident_text,
        history_text=_format_history(history),
    )


def _format_history(history: list[dict]) -> str:
    parts = []
    for i, record in enumerate(history, 1):
        parts.append(f"--- Iteration {i} ---")
        if record.get("reasoning"):
            parts.append(f"Reasoning: {record['reasoning']}")
        for cmd, result in zip(record["commands"], record["results"]):
            parts.append(f"$ {cmd}")
            parts.append(result.strip() or _NO_OUTPUT)
    return "\n".join(parts)


# ── Response parsers ──────────────────────────────────────────────────────────


def _parse_agent_json(text: str) -> dict:
    """Extract JSON from LLM response, tolerating markdown fences."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {"commands": [], "done": True, "reasoning": "parse error"}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {"commands": [], "done": True, "reasoning": "json decode error"}


def _parse_severity(text: str) -> Optional[Severity]:
    match = re.search(r"SEVERITY:\s*(CRITICAL|HIGH|MEDIUM|LOW)", text, re.IGNORECASE)
    if match:
        return _SEVERITY_MAP.get(match.group(1).upper())
    return None


# ── Findings formatter ────────────────────────────────────────────────────────


def _format_findings(history: list[dict], final_report: str) -> str:
    lines = [f"CODEBASE ANALYSIS — {len(history)} iteration(s)", "=" * 40, ""]

    lines.append("INVESTIGATION TRAIL:")
    for i, record in enumerate(history, 1):
        if record.get("reasoning"):
            lines.append(f"[Iter {i}] Reasoning: {record['reasoning']}")
        for cmd, result in zip(record["commands"], record["results"]):
            # Show first line of result as summary
            first_line = result.strip().split("\n")[0][:120] if result.strip() else _NO_OUTPUT
            lines.append(f"[Iter {i}] $ {cmd}")
            lines.append(f"         → {first_line}")
    lines.append("")

    lines.append("DIAGNOSIS:")
    lines.append(final_report.strip() if final_report else "No diagnosis generated.")

    return "\n".join(lines)


# ── Fallback (no LLM) ─────────────────────────────────────────────────────────


_STOPWORDS = {
    "the", "a", "an", "is", "in", "to", "of", "and", "or", "for", "on",
    "at", "by", "with", "this", "that", "was", "are", "be", "not", "it",
    "its", "as", "if", "from", "has", "have", "had", "but", "our", "we",
}


async def _fallback_no_llm(incident_text: str) -> ToolResult:
    """Static grep-based fallback when no LLM is available."""
    words = re.findall(r"\b[a-z][a-z0-9_]{2,}\b", incident_text.lower())
    keywords = [w for w in words if w not in _STOPWORDS][:3]
    codes = re.findall(r"\b[45]\d{2}\b", incident_text)
    search_terms = list(dict.fromkeys(keywords + codes))  # deduplicate, preserve order

    results = []
    for term in search_terms:
        out = await _run_bash(
            f"grep -rn '{term}' api/src/ web/src/ --include='*.ts' --include='*.tsx' -l"
        )
        if out and not out.startswith("["):
            results.append(f"Files matching '{term}':\n{out.strip()}")

    findings = "CODEBASE ANALYSIS (static — no LLM configured)\n" + "=" * 40 + "\n\n"
    findings += "\n\n".join(results) if results else "No keyword matches found in codebase."
    return ToolResult(
        tool_name="codebase_analyzer",
        findings=findings,
        severity_hint=None,
    )
