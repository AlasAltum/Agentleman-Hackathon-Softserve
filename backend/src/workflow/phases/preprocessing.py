from src.utils.logger import logger
from src.workflow.models import FileMetadata, IncidentInput, PreprocessedIncident


def preprocess_incident(incident: IncidentInput) -> PreprocessedIncident:
    """Route file by MIME type, extract its content, and consolidate into a clean string."""
    file_metadata = _extract_file_content(incident.file_content, incident.file_mime_type)
    consolidated_text = _consolidate_text(incident.text_desc, file_metadata.extracted_text)
    return PreprocessedIncident(
        original=incident,
        consolidated_text=consolidated_text,
        file_metadata=file_metadata,
    )


def _extract_file_content(
    file_content: bytes | None,
    mime_type: str | None,
) -> FileMetadata:
    if file_content is None:
        return FileMetadata()

    if mime_type and mime_type.startswith("text/"):
        extracted = _extract_text_log(file_content)
    elif mime_type in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        extracted = _extract_image_ocr(file_content)
    else:
        extracted = ""
        logger.warning("[preprocessing] Unsupported MIME type: %s — content skipped", mime_type)

    return FileMetadata(mime_type=mime_type, extracted_text=extracted)


def _extract_text_log(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")


def _extract_image_ocr(content: bytes) -> str:
    """Stub: returns placeholder until OCR integration is wired."""
    logger.info("[preprocessing] OCR extraction (stub — integration pending)")
    return "[image content — OCR pending integration]"


def _consolidate_text(description: str, extracted_file_text: str) -> str:
    parts = [description.strip()]
    if extracted_file_text:
        parts.append(f"[Attached content]\n{extracted_file_text.strip()}")
    return "\n\n".join(parts)