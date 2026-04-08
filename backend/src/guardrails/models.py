from dataclasses import dataclass
from enum import Enum


class ThreatLevel(str, Enum):
    SAFE = "safe"
    SUSPICIOUS = "suspicious"
    MALICIOUS = "malicious"


@dataclass
class GuardrailsResult:
    is_safe: bool
    threat_level: ThreatLevel
    blocked_patterns: list[str]
    message: str