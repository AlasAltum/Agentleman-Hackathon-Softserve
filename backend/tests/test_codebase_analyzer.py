"""Tests for the codebase_analyzer tool.

Covers:
- Pure helpers: _is_safe_command, _parse_agent_json, _parse_severity
- Bash execution: allowlist enforcement, real commands, output truncation
- Agentic loop: happy path, done=true early exit, max iterations, iterative discovery,
  unsafe commands, JSON parse errors, LLM exceptions
- Fallback (no LLM): static grep analysis
- Missing ecommerce root: graceful degradation
- Integration (real Gemini + real filesystem): end-to-end payment incident
"""

import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.workflow.models import Severity, ToolResult
from src.workflow.tools.codebase_analyzer import (
    ECOMMERCE_ROOT,
    _fallback_no_llm,
    _is_safe_command,
    _parse_agent_json,
    _parse_severity,
    _run_bash,
    analyze_codebase,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def disable_mlflow():
    """Prevent MLflow from trying to connect to a tracking server during tests."""
    with patch("src.utils.setup._setup_mlflow_callbacks"):
        yield


def _fake_llm_response(content: str) -> MagicMock:
    """Build a minimal fake LlamaIndex LLM chat() response."""
    msg = MagicMock()
    msg.content = content
    resp = MagicMock()
    resp.message = msg
    return resp


# ── Pure helper tests — no LLM, no filesystem ────────────────────────────────


class TestIsSafeCommand:
    def test_allows_grep(self):
        assert _is_safe_command("grep -rn 'error' api/src/") is True

    def test_allows_find(self):
        assert _is_safe_command("find . -name '*.ts'") is True

    def test_allows_cat(self):
        assert _is_safe_command("cat api/src/modules/stub-payment/service.ts") is True

    def test_allows_head(self):
        assert _is_safe_command("head -n 50 web/src/app/page.tsx") is True

    def test_allows_ls(self):
        assert _is_safe_command("ls api/src/") is True

    def test_blocks_rm(self):
        assert _is_safe_command("rm -rf /") is False

    def test_blocks_curl(self):
        assert _is_safe_command("curl http://evil.com") is False

    def test_blocks_python(self):
        assert _is_safe_command("python -c 'import os; os.system(\"id\")'") is False

    def test_blocks_empty(self):
        assert _is_safe_command("") is False

    def test_blocks_shell_injection(self):
        # shlex.split splits on semicolon only when unquoted —
        # "ls; rm" splits into ["ls;", "rm", "-rf", "/"], first token "ls;" not in allowlist
        assert _is_safe_command("ls; rm -rf /") is False


class TestParseAgentJson:
    def test_clean_json(self):
        text = '{"reasoning": "found it", "commands": ["grep -rn foo api/"], "done": false}'
        result = _parse_agent_json(text)
        assert result["done"] is False
        assert result["commands"] == ["grep -rn foo api/"]

    def test_markdown_fenced_json(self):
        text = '```json\n{"reasoning": "x", "commands": [], "done": true}\n```'
        result = _parse_agent_json(text)
        assert result["done"] is True

    def test_invalid_json_returns_done_true(self):
        result = _parse_agent_json("this is not json at all")
        assert result["done"] is True
        assert result["commands"] == []

    def test_empty_string(self):
        result = _parse_agent_json("")
        assert result["done"] is True

    def test_json_embedded_in_prose(self):
        text = 'Here is my plan:\n{"commands": ["ls api/"], "done": false}\nEnd.'
        result = _parse_agent_json(text)
        assert result["commands"] == ["ls api/"]


class TestParseSeverity:
    def test_parses_critical(self):
        assert _parse_severity("SEVERITY: CRITICAL") == Severity.CRITICAL

    def test_parses_high(self):
        assert _parse_severity("some text\nSEVERITY: HIGH\nmore text") == Severity.HIGH

    def test_parses_medium(self):
        assert _parse_severity("SEVERITY: MEDIUM") == Severity.MEDIUM

    def test_parses_low(self):
        assert _parse_severity("SEVERITY: LOW") == Severity.LOW

    def test_case_insensitive(self):
        assert _parse_severity("severity: critical") == Severity.CRITICAL

    def test_missing_returns_none(self):
        assert _parse_severity("No severity line here.") is None


# ── _run_bash tests ───────────────────────────────────────────────────────────


class TestRunBash:
    @pytest.mark.asyncio
    async def test_blocked_command_returns_message(self):
        result = await _run_bash("rm -rf /")
        assert "[command not allowed" in result

    @pytest.mark.asyncio
    async def test_safe_ls_executes(self):
        # ls /tmp always works — override cwd so it doesn't depend on ecommerce-platform
        with patch("src.workflow.tools.codebase_analyzer.ECOMMERCE_ROOT", "/tmp"):
            result = await _run_bash("ls /tmp")
        assert "[command not allowed" not in result
        assert "[command failed" not in result

    @pytest.mark.asyncio
    async def test_nonexistent_path_does_not_crash(self):
        result = await _run_bash("find /nonexistent_path_xyz -name '*.ts'")
        # find returns non-zero but we suppress stderr; result is empty or error msg
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_output_is_string(self):
        if not Path(ECOMMERCE_ROOT).exists():
            pytest.skip("ecommerce-platform not available")
        result = await _run_bash("find . -name '*.ts' -maxdepth 3")
        assert isinstance(result, str)


# ── analyze_codebase agentic loop (mocked LLM) ───────────────────────────────


class TestAgenticLoop:
    """LLM is mocked — no API calls, no MLflow, bash may or may not be mocked."""

    @pytest.fixture(autouse=True)
    def mock_ecommerce_root_exists(self):
        """Make the ecommerce root path check pass regardless of local filesystem."""
        with patch("src.workflow.tools.codebase_analyzer.Path") as MockPath:
            inst = MagicMock()
            inst.exists.return_value = True
            MockPath.return_value = inst
            yield

    @pytest.mark.asyncio
    async def test_happy_path_returns_critical(self):
        """Boot → one iteration → final report → CRITICAL severity."""
        boot = _fake_llm_response(
            '{"reasoning": "check payment", '
            '"commands": ["grep -rn \'shouldFail\' api/src/ --include=\'*.ts\'"], "done": false}'
        )
        iteration = _fake_llm_response(
            '{"reasoning": "found it, reading file", '
            '"commands": ["cat api/src/modules/stub-payment/service.ts"], "done": true}'
        )
        final = _fake_llm_response(
            "ROOT CAUSE: stub-payment/service.ts — STUB_PAYMENT_CONFIG.shouldFail=true\n"
            "EXPLANATION: All payments fail intentionally.\n"
            "AFFECTED PATHS: Checkout flow\n"
            "RECOMMENDED ACTION: Set shouldFail=false\n"
            "SEVERITY: CRITICAL"
        )
        llm = MagicMock()
        llm.chat.side_effect = [boot, iteration, final]

        with patch("src.workflow.tools.codebase_analyzer._get_llm", return_value=llm), \
             patch("src.workflow.tools.codebase_analyzer._run_bash", new_callable=AsyncMock) as bash:
            bash.return_value = "api/src/modules/stub-payment/service.ts:12:  shouldFail: true,"
            result = await analyze_codebase("payment authorization error 500")

        assert isinstance(result, ToolResult)
        assert result.tool_name == "codebase_analyzer"
        assert result.severity_hint == Severity.CRITICAL
        assert "INVESTIGATION TRAIL" in result.findings
        assert "DIAGNOSIS" in result.findings

    @pytest.mark.asyncio
    async def test_done_true_on_boot_skips_iteration(self):
        """If boot response has done=true, no iteration prompt is sent."""
        boot = _fake_llm_response(
            '{"reasoning": "nothing needed", "commands": ["ls api/src/"], "done": true}'
        )
        final = _fake_llm_response("ROOT CAUSE: nothing.\nSEVERITY: LOW")
        llm = MagicMock()
        llm.chat.side_effect = [boot, final]

        with patch("src.workflow.tools.codebase_analyzer._get_llm", return_value=llm), \
             patch("src.workflow.tools.codebase_analyzer._run_bash", new_callable=AsyncMock) as bash:
            bash.return_value = "api/src/"
            result = await analyze_codebase("minor incident")

        assert result.severity_hint == Severity.LOW
        # boot call + final report call only (no iteration in between)
        assert llm.chat.call_count == 2

    @pytest.mark.asyncio
    async def test_max_iterations_stops_loop(self):
        """Loop stops at MAX_ITERATIONS even if LLM never sets done=true."""
        never_done = _fake_llm_response(
            '{"reasoning": "keep looking", "commands": ["ls ."], "done": false}'
        )
        final = _fake_llm_response("ROOT CAUSE: unknown.\nSEVERITY: MEDIUM")
        llm = MagicMock()
        llm.chat.side_effect = [never_done] * 5 + [final]

        with patch("src.workflow.tools.codebase_analyzer._get_llm", return_value=llm), \
             patch("src.workflow.tools.codebase_analyzer._run_bash", new_callable=AsyncMock) as bash:
            bash.return_value = "[no output]"
            result = await analyze_codebase("mystery incident")

        assert result.severity_hint == Severity.MEDIUM
        # boot + up to 4 iteration prompts + final = at most 6 calls for MAX_ITERATIONS=5
        assert llm.chat.call_count <= 6

    @pytest.mark.asyncio
    async def test_iterative_discovery_follows_code_trace(self):
        """Agent searches checkout → finds import → follows to payment → done."""
        boot = _fake_llm_response(
            '{"reasoning": "search checkout", '
            '"commands": ["grep -rn \'checkout\' web/src/ -l"], "done": false}'
        )
        iter1 = _fake_llm_response(
            '{"reasoning": "found checkout, reading it", '
            '"commands": ["cat web/src/modules/checkout/index.ts"], "done": false}'
        )
        iter2 = _fake_llm_response(
            '{"reasoning": "checkout calls payment — enough evidence", "commands": [], "done": true}'
        )
        final = _fake_llm_response(
            "ROOT CAUSE: checkout calls broken payment module.\nSEVERITY: HIGH"
        )
        llm = MagicMock()
        llm.chat.side_effect = [boot, iter1, iter2, final]

        with patch("src.workflow.tools.codebase_analyzer._get_llm", return_value=llm), \
             patch("src.workflow.tools.codebase_analyzer._run_bash", new_callable=AsyncMock) as bash:
            bash.side_effect = [
                "web/src/modules/checkout/index.ts",
                "import { authorize } from '../../payment/service'",
                "",
            ]
            result = await analyze_codebase("checkout broken, users can't complete orders")

        assert result.severity_hint == Severity.HIGH
        assert "INVESTIGATION TRAIL" in result.findings
        assert llm.chat.call_count == 4

    @pytest.mark.asyncio
    async def test_unsafe_commands_blocked_but_safe_ones_run(self):
        """Disallowed commands get '[command not allowed]' in output; loop continues."""
        boot = _fake_llm_response(
            '{"reasoning": "try something", "commands": ["rm -rf /", "ls api/src/"], "done": true}'
        )
        final = _fake_llm_response("ROOT CAUSE: none.\nSEVERITY: LOW")
        llm = MagicMock()
        llm.chat.side_effect = [boot, final]

        with patch("src.workflow.tools.codebase_analyzer._get_llm", return_value=llm):
            result = await analyze_codebase("some incident")

        assert result.tool_name == "codebase_analyzer"
        assert "[command not allowed" in result.findings

    @pytest.mark.asyncio
    async def test_llm_returns_malformed_json_does_not_crash(self):
        """Malformed JSON in boot → parsed as done=true → goes straight to final report."""
        boot = _fake_llm_response("not json at all, I give up")
        final = _fake_llm_response("ROOT CAUSE: could not investigate.\nSEVERITY: LOW")
        llm = MagicMock()
        llm.chat.side_effect = [boot, final]

        with patch("src.workflow.tools.codebase_analyzer._get_llm", return_value=llm), \
             patch("src.workflow.tools.codebase_analyzer._run_bash", new_callable=AsyncMock) as bash:
            bash.return_value = "[no output]"
            result = await analyze_codebase("error in production")

        assert isinstance(result, ToolResult)
        assert result.tool_name == "codebase_analyzer"

    @pytest.mark.asyncio
    async def test_llm_exception_does_not_propagate(self):
        """If LLM raises mid-loop, analyze_codebase() catches it and returns a ToolResult."""
        llm = MagicMock()
        llm.chat.side_effect = RuntimeError("API quota exceeded")

        with patch("src.workflow.tools.codebase_analyzer._get_llm", return_value=llm):
            result = await analyze_codebase("500 internal server error")

        assert isinstance(result, ToolResult)
        assert result.tool_name == "codebase_analyzer"


# ── Fallback: no LLM configured ──────────────────────────────────────────────


class TestFallbackNoLlm:
    @pytest.mark.asyncio
    async def test_returns_tool_result_with_no_severity(self):
        with patch("src.workflow.tools.codebase_analyzer._run_bash", new_callable=AsyncMock) as bash:
            bash.return_value = "api/src/modules/stub-payment/service.ts"
            result = await _fallback_no_llm("payment authorization error")

        assert isinstance(result, ToolResult)
        assert result.tool_name == "codebase_analyzer"
        assert result.severity_hint is None

    @pytest.mark.asyncio
    async def test_findings_include_keyword(self):
        with patch("src.workflow.tools.codebase_analyzer._run_bash", new_callable=AsyncMock) as bash:
            bash.return_value = "api/src/modules/stub-payment/service.ts"
            result = await _fallback_no_llm("payment error 500")

        assert any(
            kw in result.findings for kw in ("payment", "error", "500", "Files matching")
        )

    @pytest.mark.asyncio
    async def test_no_matches_graceful_message(self):
        with patch("src.workflow.tools.codebase_analyzer._run_bash", new_callable=AsyncMock) as bash:
            bash.return_value = "[no output]"
            result = await _fallback_no_llm("zzzzzzzzz obscure incident")

        assert "No keyword matches found" in result.findings

    @pytest.mark.asyncio
    async def test_analyze_codebase_uses_fallback_when_no_llm(self):
        with patch("src.workflow.tools.codebase_analyzer.Path") as MockPath, \
             patch("src.workflow.tools.codebase_analyzer._get_llm", return_value=None), \
             patch("src.workflow.tools.codebase_analyzer._run_bash", new_callable=AsyncMock) as bash:
            inst = MagicMock()
            inst.exists.return_value = True
            MockPath.return_value = inst
            bash.return_value = "api/src/modules/stub-payment/service.ts"
            result = await analyze_codebase("payment error")

        assert "static" in result.findings.lower()
        assert result.severity_hint is None


# ── Missing ecommerce root ────────────────────────────────────────────────────


class TestMissingEcommerceRoot:
    @pytest.mark.asyncio
    async def test_graceful_message_when_root_missing(self):
        with patch("src.workflow.tools.codebase_analyzer.Path") as MockPath:
            inst = MagicMock()
            inst.exists.return_value = False
            MockPath.return_value = inst

            with patch("src.workflow.tools.codebase_analyzer._get_llm", return_value=MagicMock()):
                result = await analyze_codebase("500 error")

        assert isinstance(result, ToolResult)
        assert result.severity_hint is None
        assert "not found" in result.findings.lower() or "Skipping" in result.findings


# ── Real filesystem bash (no LLM) ────────────────────────────────────────────


class TestRealFilesystem:
    """Exercises actual bash commands on ecommerce-platform/.
    Skipped automatically if the directory is not present."""

    @pytest.mark.asyncio
    async def test_find_ts_files(self):
        if not Path(ECOMMERCE_ROOT).exists():
            pytest.skip("ecommerce-platform not available")
        result = await _run_bash("find . -name '*.ts' -not -name '*.d.ts' -maxdepth 4")
        assert ".ts" in result

    @pytest.mark.asyncio
    async def test_grep_payment_finds_files(self):
        if not Path(ECOMMERCE_ROOT).exists():
            pytest.skip("ecommerce-platform not available")
        result = await _run_bash("grep -rn 'payment' api/src/ --include='*.ts' -l")
        assert "[command failed" not in result

    @pytest.mark.asyncio
    async def test_should_fail_flag_detectable(self):
        if not Path(ECOMMERCE_ROOT).exists():
            pytest.skip("ecommerce-platform not available")
        result = await _run_bash("grep -rn 'shouldFail' api/src/ --include='*.ts'")
        assert isinstance(result, str)
        # If the stub payment bug is present, shouldFail:true must appear
        if result and not result.startswith("["):
            assert "shouldFail" in result

    @pytest.mark.asyncio
    async def test_full_loop_mocked_llm_real_bash(self):
        """Real bash commands + mocked LLM = deterministic end-to-end test."""
        if not Path(ECOMMERCE_ROOT).exists():
            pytest.skip("ecommerce-platform not available")

        boot = _fake_llm_response(
            '{"reasoning": "payment incident — check stub-payment config", '
            '"commands": ["grep -rn \'shouldFail\' api/src/ --include=\'*.ts\'"], "done": false}'
        )
        iteration = _fake_llm_response(
            '{"reasoning": "found shouldFail, enough evidence", "commands": [], "done": true}'
        )
        final = _fake_llm_response(
            "ROOT CAUSE: api/src/modules/stub-payment/service.ts — shouldFail: true\n"
            "EXPLANATION: Stub payment config intentionally fails all authorizations.\n"
            "AFFECTED PATHS: All checkout payment flows.\n"
            "RECOMMENDED ACTION: Set shouldFail=false or replace with real payment provider.\n"
            "SEVERITY: CRITICAL"
        )
        llm = MagicMock()
        llm.chat.side_effect = [boot, iteration, final]

        with patch("src.workflow.tools.codebase_analyzer._get_llm", return_value=llm):
            result = await analyze_codebase("payment authorization failed with 500 error")

        assert result.tool_name == "codebase_analyzer"
        assert result.severity_hint == Severity.CRITICAL
        assert "INVESTIGATION TRAIL" in result.findings
        assert "DIAGNOSIS" in result.findings


# ── Real Gemini integration test ──────────────────────────────────────────────


@pytest.mark.integration
class TestRealGeminiIntegration:
    """Uses the real Gemini LLM (requires GEMINI_API_KEY or GOOGLE_API_KEY in .env).
    Marked with @pytest.mark.integration — run with: pytest -m integration
    """

    @pytest.mark.asyncio
    async def test_payment_incident_produces_critical_finding(self):
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("No Gemini API key configured")
        if not Path(ECOMMERCE_ROOT).exists():
            pytest.skip("ecommerce-platform not available")

        from src.utils.setup import setup_defaults, reset_settings
        os.environ["LLM_PROVIDER"] = "gemini"
        os.environ["EMBED_PROVIDER"] = "mock"
        setup_defaults()

        try:
            result = await analyze_codebase(
                "Payment authorization is failing for all users. "
                "The checkout flow returns a 500 error on every payment attempt. "
                "Suspected bug in the payment processing module."
            )
        finally:
            reset_settings()

        assert isinstance(result, ToolResult)
        assert result.tool_name == "codebase_analyzer"
        assert result.findings  # non-empty
        assert "INVESTIGATION TRAIL" in result.findings
        # With shouldFail:true in the codebase, Gemini should detect CRITICAL
        assert result.severity_hint in (Severity.CRITICAL, Severity.HIGH)

    @pytest.mark.asyncio
    async def test_low_severity_typo_incident(self):
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("No Gemini API key configured")
        if not Path(ECOMMERCE_ROOT).exists():
            pytest.skip("ecommerce-platform not available")

        from src.utils.setup import setup_defaults, reset_settings
        os.environ["LLM_PROVIDER"] = "gemini"
        os.environ["EMBED_PROVIDER"] = "mock"
        setup_defaults()

        try:
            result = await analyze_codebase(
                "There is a minor typo in the product description label. "
                "It says 'Prcie' instead of 'Price'."
            )
        finally:
            reset_settings()

        assert isinstance(result, ToolResult)
        assert result.findings
        # Non-payment incidents should not be CRITICAL
        assert result.severity_hint != Severity.CRITICAL
