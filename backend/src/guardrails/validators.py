import re

from src.guardrails.base import BaseGuardrail
from src.guardrails.models import GuardrailsResult, ThreatLevel
from src.utils.logger import logger

# ── File magic-byte signatures ────────────────────────────────────────────────
# Maps MIME types to (offset, magic_bytes) tuples.  We only validate types that
# have well-known magic numbers; text-based formats are validated structurally.

_MAGIC_SIGNATURES: dict[str, list[tuple[int, bytes]]] = {
    "image/png": [(0, b"\x89PNG\r\n\x1a\n")],
    "image/jpeg": [(0, b"\xff\xd8\xff")],
    "image/gif": [(0, b"GIF87a"), (0, b"GIF89a")],
    "image/webp": [(0, b"RIFF"), (8, b"WEBP")],  # RIFF....WEBP
    "application/pdf": [(0, b"%PDF")],
}

# Dangerous byte sequences that should never appear in uploaded files
_DANGEROUS_BYTE_PATTERNS: list[tuple[bytes, str]] = [
    (b"MZ", "Windows PE executable"),
    (b"\x7fELF", "Linux ELF executable"),
    (b"#!/", "Shell script shebang"),
    (b"PK\x03\x04", "ZIP/Office archive"),
]

# ── XSS ───────────────────────────────────────────────────────────────────────


class XssGuardrail(BaseGuardrail):
    """Detects XSS via both literal patterns and regex for encoded/obfuscated variants."""

    _LITERAL_PATTERNS = [
        "<script",
        "</script>",
        "javascript:",
        "vbscript:",
        "data:text/html",
    ]

    _REGEX_PATTERNS = [
        # Event handlers (onerror, onload, onclick, onmouseover, onfocus …)
        re.compile(r"\bon\w+\s*=", re.IGNORECASE),
        # <tag with suspicious attributes
        re.compile(r"<\s*(iframe|object|embed|form|base|meta|link)\b", re.IGNORECASE),
        # Expression / eval injection
        re.compile(r"expression\s*\(", re.IGNORECASE),
        # document.cookie / document.location / document.write
        re.compile(r"document\s*\.\s*(cookie|location|write)", re.IGNORECASE),
        # String.fromCharCode obfuscation
        re.compile(r"String\s*\.\s*fromCharCode", re.IGNORECASE),
        # HTML entity encoded script tags  &#60;script  or  &#x3c;script
        re.compile(r"&#(x3c|60);?\s*script", re.IGNORECASE),
        # SVG-based XSS
        re.compile(r"<\s*svg[^>]*\bon\w+\s*=", re.IGNORECASE),
    ]

    def validate(self, content: str) -> GuardrailsResult:
        text_lower = content.lower()
        blocked: list[str] = []

        for p in self._LITERAL_PATTERNS:
            if p in text_lower:
                blocked.append(p)

        for rx in self._REGEX_PATTERNS:
            if rx.search(content):
                blocked.append(rx.pattern)

        if blocked:
            logger.warning(
                "guardrail_blocked",
                phase="guardrails",
                component="XssGuardrail",
                status="error",
                threat_level=ThreatLevel.MALICIOUS.value,
                blocked_patterns=blocked,
            )
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.MALICIOUS,
                blocked_patterns=blocked,
                message="Potential XSS attack detected.",
            )

        return GuardrailsResult(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            blocked_patterns=[],
            message="No XSS patterns detected.",
        )


# ── SQL Injection ─────────────────────────────────────────────────────────────


class SqlInjectionGuardrail(BaseGuardrail):
    """Regex-based SQL injection detection covering common attack vectors."""

    _PATTERNS = [
        # Classic tautologies
        re.compile(r"'\s*OR\s+['\d].*=", re.IGNORECASE),
        re.compile(r"'\s*OR\s+1\s*=\s*1", re.IGNORECASE),
        re.compile(r"\bOR\s+1\s*=\s*1\b", re.IGNORECASE),
        # UNION-based injection
        re.compile(r"\bUNION\s+(ALL\s+)?SELECT\b", re.IGNORECASE),
        # Destructive statements
        re.compile(r"\bDROP\s+(TABLE|DATABASE|INDEX)\b", re.IGNORECASE),
        re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
        re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),
        re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
        re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
        re.compile(r"\bUPDATE\s+\w+\s+SET\b", re.IGNORECASE),
        # Comment-based bypass
        re.compile(r";\s*--", re.IGNORECASE),
        re.compile(r"/\*.*?\*/", re.IGNORECASE | re.DOTALL),
        # Stacked queries
        re.compile(r";\s*(SELECT|DROP|INSERT|UPDATE|DELETE|EXEC)\b", re.IGNORECASE),
        # EXEC / xp_ stored procedures (MSSQL)
        re.compile(r"\bEXEC\s*\(", re.IGNORECASE),
        re.compile(r"\bxp_\w+", re.IGNORECASE),
        # SLEEP / BENCHMARK (time-based blind)
        re.compile(r"\bSLEEP\s*\(", re.IGNORECASE),
        re.compile(r"\bBENCHMARK\s*\(", re.IGNORECASE),
        re.compile(r"\bWAITFOR\s+DELAY\b", re.IGNORECASE),
        # LOAD_FILE / INTO OUTFILE (file access)
        re.compile(r"\bLOAD_FILE\s*\(", re.IGNORECASE),
        re.compile(r"\bINTO\s+(OUT|DUMP)FILE\b", re.IGNORECASE),
    ]

    def validate(self, content: str) -> GuardrailsResult:
        blocked: list[str] = []

        for rx in self._PATTERNS:
            if rx.search(content):
                blocked.append(rx.pattern)

        if blocked:
            logger.warning(
                "guardrail_blocked",
                phase="guardrails",
                component="SqlInjectionGuardrail",
                status="error",
                threat_level=ThreatLevel.MALICIOUS.value,
                blocked_patterns=blocked,
            )
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.MALICIOUS,
                blocked_patterns=blocked,
                message="Potential SQL injection detected.",
            )

        return GuardrailsResult(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            blocked_patterns=[],
            message="No SQL injection patterns detected.",
        )


# ── Code / Command Execution ─────────────────────────────────────────────────


class CodeExecutionGuardrail(BaseGuardrail):
    """Detects shell injection, OS command execution, and code-eval patterns."""

    _PATTERNS = [
        # Shell command chaining / piping
        re.compile(r"[;&|`]\s*(cat|ls|rm|wget|curl|bash|sh|python|perl|ruby|nc|ncat)\b", re.IGNORECASE),
        # Backtick / $() command substitution
        re.compile(r"`[^`]+`"),
        re.compile(r"\$\([^)]+\)"),
        # Common dangerous commands
        re.compile(r"\b(eval|exec|system|popen|subprocess|os\.system|os\.popen)\s*\(", re.IGNORECASE),
        # PowerShell
        re.compile(r"\b(Invoke-Expression|Invoke-WebRequest|IEX|iex)\b", re.IGNORECASE),
        # Python/Ruby/Node inline execution
        re.compile(r"\b(python|ruby|node|perl)\s+-[ec]\s+", re.IGNORECASE),
        # Reverse shell patterns
        re.compile(r"\b(nc|ncat|netcat)\s+-[elp]", re.IGNORECASE),
        re.compile(r"/dev/(tcp|udp)/", re.IGNORECASE),
        # Base64 decode piped to shell
        re.compile(r"base64\s+(-d|--decode).*\|\s*(bash|sh)", re.IGNORECASE),
    ]

    def validate(self, content: str) -> GuardrailsResult:
        blocked: list[str] = []

        for rx in self._PATTERNS:
            if rx.search(content):
                blocked.append(rx.pattern)

        if blocked:
            logger.warning(
                "guardrail_blocked",
                phase="guardrails",
                component="CodeExecutionGuardrail",
                status="error",
                threat_level=ThreatLevel.MALICIOUS.value,
                blocked_patterns=blocked,
            )
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.MALICIOUS,
                blocked_patterns=blocked,
                message="Potential code/command execution attempt detected.",
            )

        return GuardrailsResult(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            blocked_patterns=[],
            message="No code execution patterns detected.",
        )


# ── Path Traversal ────────────────────────────────────────────────────────────


class PathTraversalGuardrail(BaseGuardrail):
    """Detects directory traversal and sensitive file-path references."""

    _PATTERNS = [
        # Classic traversal
        re.compile(r"\.\./"),
        re.compile(r"\.\.\\"),
        # URL-encoded traversal
        re.compile(r"%2e%2e[/\\%]", re.IGNORECASE),
        re.compile(r"\.%2e[/\\]", re.IGNORECASE),
        re.compile(r"%2e\.[/\\]", re.IGNORECASE),
        # Sensitive Unix paths
        re.compile(r"/etc/(passwd|shadow|hosts|sudoers)", re.IGNORECASE),
        re.compile(r"/proc/self/", re.IGNORECASE),
        # Sensitive Windows paths
        re.compile(r"[A-Za-z]:\\(Windows|System32|boot\.ini)", re.IGNORECASE),
    ]

    def validate(self, content: str) -> GuardrailsResult:
        blocked: list[str] = []

        for rx in self._PATTERNS:
            if rx.search(content):
                blocked.append(rx.pattern)

        if blocked:
            logger.warning(
                "guardrail_blocked",
                phase="guardrails",
                component="PathTraversalGuardrail",
                status="error",
                threat_level=ThreatLevel.MALICIOUS.value,
                blocked_patterns=blocked,
            )
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.MALICIOUS,
                blocked_patterns=blocked,
                message="Potential path traversal attack detected.",
            )

        return GuardrailsResult(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            blocked_patterns=[],
            message="No path traversal patterns detected.",
        )


# ── Content-Type / MIME validation ────────────────────────────────────────────


class ContentTypeGuardrail(BaseGuardrail):
    """Validates MIME type against an allow-list."""

    def __init__(self, allowed_mime_types: list[str] | None = None):
        self._allowed_mime_types = allowed_mime_types or [
            # Text / logs
            "text/plain",
            "text/log",
            # Structured data
            "application/json",
            "text/csv",
            "application/csv",
            # Images
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
        ]

    def validate(self, content: str, mime_type: str | None = None) -> GuardrailsResult:
        if mime_type is None:
            return GuardrailsResult(
                is_safe=True,
                threat_level=ThreatLevel.SAFE,
                blocked_patterns=[],
                message="No file content to validate.",
            )

        if mime_type not in self._allowed_mime_types:
            logger.warning(
                "guardrail_blocked",
                phase="guardrails",
                component="ContentTypeGuardrail",
                status="error",
                threat_level=ThreatLevel.SUSPICIOUS.value,
                mime_type=mime_type,
            )
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.SUSPICIOUS,
                blocked_patterns=[f"mime:{mime_type}"],
                message=f"Disallowed MIME type: {mime_type}",
            )

        return GuardrailsResult(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            blocked_patterns=[],
            message="MIME type allowed.",
        )


# ── File Magic-Byte Validation ────────────────────────────────────────────────


class FileMagicBytesGuardrail:
    """Validates that file bytes actually match the claimed MIME type.

    MIME types sent by the browser are trivially spoofable.  This guardrail
    reads the first bytes of the file and compares them against known magic
    signatures.  It also scans for dangerous executable headers that should
    never appear in SRE incident attachments.
    """

    _MAX_SCAN_BYTES = 512  # only inspect the header

    def validate(self, file_bytes: bytes, claimed_mime: str, file_name: str = "") -> GuardrailsResult:
        # 1. Reject known executable signatures regardless of claimed type
        header = file_bytes[: self._MAX_SCAN_BYTES]
        for sig, label in _DANGEROUS_BYTE_PATTERNS:
            if header.startswith(sig):
                logger.warning(
                    "guardrail_blocked",
                    phase="guardrails",
                    component="FileMagicBytesGuardrail",
                    file_name=file_name,
                    reason=f"Executable signature detected: {label}",
                )
                return GuardrailsResult(
                    is_safe=False,
                    threat_level=ThreatLevel.MALICIOUS,
                    blocked_patterns=[f"exec_sig:{label}"],
                    message=f"File rejected: detected {label} signature.",
                )

        # 2. For types with known magic bytes, verify the header matches
        expected_sigs = _MAGIC_SIGNATURES.get(claimed_mime)
        if expected_sigs is not None:
            matched = False
            for offset, magic in expected_sigs:
                if file_bytes[offset: offset + len(magic)] == magic:
                    matched = True
                    break

            # WebP requires both RIFF at 0 and WEBP at 8
            if claimed_mime == "image/webp":
                riff_ok = file_bytes[0:4] == b"RIFF"
                webp_ok = file_bytes[8:12] == b"WEBP"
                matched = riff_ok and webp_ok

            if not matched:
                logger.warning(
                    "guardrail_blocked",
                    phase="guardrails",
                    component="FileMagicBytesGuardrail",
                    file_name=file_name,
                    claimed_mime=claimed_mime,
                    reason="Magic bytes do not match claimed MIME type",
                )
                return GuardrailsResult(
                    is_safe=False,
                    threat_level=ThreatLevel.MALICIOUS,
                    blocked_patterns=[f"magic_mismatch:{claimed_mime}"],
                    message=f"File content does not match claimed type ({claimed_mime}).",
                )

        return GuardrailsResult(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            blocked_patterns=[],
            message="File magic bytes validated.",
        )


# ── Input Size Guardrail ──────────────────────────────────────────────────────

_MAX_TEXT_LENGTH = 50_000  # characters
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class InputSizeGuardrail(BaseGuardrail):
    """Rejects oversized text payloads that could abuse downstream LLM calls."""

    def __init__(self, max_length: int = _MAX_TEXT_LENGTH):
        self._max_length = max_length

    def validate(self, content: str) -> GuardrailsResult:
        if len(content) > self._max_length:
            logger.warning(
                "guardrail_blocked",
                phase="guardrails",
                component="InputSizeGuardrail",
                content_length=len(content),
                max_length=self._max_length,
            )
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.SUSPICIOUS,
                blocked_patterns=["oversized_input"],
                message=f"Input too large ({len(content)} chars, max {self._max_length}).",
            )

        return GuardrailsResult(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            blocked_patterns=[],
            message="Input size within limits.",
        )
