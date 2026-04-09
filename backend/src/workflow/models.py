from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class IncidentType(str, Enum):
    ALERT_STORM = "alert_storm"
    HISTORICAL_REGRESSION = "historical_regression"
    NEW_INCIDENT = "new_incident"

# TODO: Alonso: We could add severity scoring as an extra
# If we have enough time
class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IncidentInput(BaseModel):
    text_desc: str
    reporter_email: str
    file_contents: list[bytes] = []
    file_mime_types: list[str] = []
    file_names: list[str] = []


class FileMetadata(BaseModel):
    mime_types: list[str] = []
    extracted_text: str = ""


class PreprocessedIncident(BaseModel):
    original: IncidentInput
    consolidated_text: str
    file_metadata: FileMetadata = FileMetadata()
    security_flag: Optional[str] = None
    request_id: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}


class HistoricalCandidate(BaseModel):
    incident_id: str
    timestamp: datetime
    description: str
    resolution: Optional[str] = None
    similarity_score: float


class ClassificationResult(BaseModel):
    incident_type: IncidentType
    top_candidates: list[HistoricalCandidate] = []
    historical_rca: Optional[str] = None


class ToolResult(BaseModel):
    tool_name: str
    findings: str
    severity_hint: Optional[Severity] = None


class TriageResult(BaseModel):
    classification: ClassificationResult
    tool_results: list[ToolResult]
    technical_summary: str
    severity: Severity
    business_impact_summary: str


class TicketInfo(BaseModel):
    ticket_id: str
    ticket_url: str
    reporter_email: str
    action: str  # "created" or "updated"
    title: str = ""
    description: str = ""
    request_id: Optional[str] = None


class ResolutionPayload(BaseModel):
    ticket_id: str
    resolved_by: str
    resolution_notes: str
    reporter_email: Optional[str] = None
    request_id: Optional[str] = None
