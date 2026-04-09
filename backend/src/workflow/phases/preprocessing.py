import asyncio
import base64
import csv
import io
import json
import os

from src.utils.logger import logger
from src.workflow.models import FileMetadata, IncidentInput, PreprocessedIncident

# Extension sets for routing when MIME type is ambiguous
_JSON_EXTENSIONS = {".json"}
_CSV_EXTENSIONS = {".csv"}
_BLOCKED_EXTENSIONS = {".tf", ".tfvars", ".yaml", ".yml"}

_CSV_MAX_ROWS = 100

_OCR_PROMPT = (
    "Extract all visible text from this image. Focus on error messages, stack traces, "
    "metrics, dashboard panels, terminal output, or any technical information relevant "
    "to an SRE incident. If no text is present, describe the technical content shown."
)


async def preprocess_incident(incident: IncidentInput) -> PreprocessedIncident:
    """Route files by MIME type / extension, extract content, consolidate into clean string."""
    extracted_texts: list[str] = []
    mime_types: list[str] = []

    for content, mime_type, file_name in zip(
        incident.file_contents, incident.file_mime_types, incident.file_names
    ):
        ext = _file_extension(file_name)
        if ext in _BLOCKED_EXTENSIONS:
            logger.warning("blocked_file_extension", file_name=file_name, ext=ext)
            raise ValueError(f"File type not allowed: {ext}")

        file_metadata = await _extract_file_content(content, mime_type, file_name)
        extracted_texts.append(file_metadata.extracted_text)
        mime_types.append(mime_type)

    file_metadata = FileMetadata(mime_types=mime_types, extracted_text="\n\n".join(extracted_texts))
    consolidated_text = _consolidate_text(incident.text_desc, file_metadata.extracted_text)
    return PreprocessedIncident(
        original=incident,
        consolidated_text=consolidated_text,
        file_metadata=file_metadata,
    )


async def _extract_file_content(
    file_content: bytes,
    mime_type: str,
    file_name: str,
) -> FileMetadata:
    ext = _file_extension(file_name)

    if ext in _JSON_EXTENSIONS or mime_type == "application/json":
        extracted = _extract_json(file_content)
    elif ext in _CSV_EXTENSIONS or mime_type in ("text/csv", "application/csv"):
        extracted = _extract_csv(file_content)
    elif mime_type in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        extracted = await _extract_image_ocr(file_content, mime_type)
    elif mime_type and mime_type.startswith("text/"):
        extracted = _extract_text_log(file_content)
    else:
        extracted = ""
        logger.warning("unsupported_mime_type", mime_type=mime_type)

    return FileMetadata(mime_types=[mime_type], extracted_text=extracted)


def _file_extension(file_name: str | None) -> str:
    if not file_name:
        return ""
    return os.path.splitext(file_name)[1].lower()


# ── Text / log ───────────────────────────────────────────────────────────────

def _extract_text_log(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")


# ── JSON ─────────────────────────────────────────────────────────────────────

def _extract_json(content: bytes) -> str:
    try:
        data = json.loads(content.decode("utf-8", errors="replace"))
        return json.dumps(data, indent=2, ensure_ascii=False)
    except json.JSONDecodeError as exc:
        logger.warning("json_parse_error", error=str(exc))
        return content.decode("utf-8", errors="replace")


# ── CSV ───────────────────────────────────────────────────────────────────────

def _extract_csv(content: bytes) -> str:
    try:
        text = content.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        lines: list[str] = []
        for i, row in enumerate(reader):
            if i >= _CSV_MAX_ROWS:
                lines.append(f"[... truncated after {_CSV_MAX_ROWS} rows]")
                break
            lines.append(", ".join(f"{k}={v}" for k, v in row.items()))
        return f"CSV ({len(lines)} rows):\n" + "\n".join(lines)
    except Exception as exc:
        logger.warning("csv_parse_error", error=str(exc))
        return content.decode("utf-8", errors="replace")


# ── Image OCR (Gemini multimodal) ─────────────────────────────────────────────

async def _extract_image_ocr(content: bytes, mime_type: str) -> str:
    api_key = (
        os.getenv("GOOGLE_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("LLM_API_KEY")
    )

    if not api_key:
        logger.warning("no_api_key_configured", integration="gemini_ocr")
        return "[image attached — OCR requires GOOGLE_API_KEY or GEMINI_API_KEY]"

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        image_part = {"mime_type": mime_type, "data": base64.b64encode(content).decode()}

        # Run in thread pool — google-generativeai generate_content is sync
        response = await asyncio.to_thread(
            model.generate_content,
            [_OCR_PROMPT, image_part],
        )
        extracted = response.text.strip()
        logger.info("ocr_extraction_complete", characters=len(extracted))
        return extracted

    except ImportError:
        logger.warning("google_generativeai_not_installed")
        return "[image attached — install google-generativeai for OCR support]"
    except Exception as exc:
        logger.warning("ocr_failed", error=str(exc))
        return "[image attached — OCR extraction failed]"


# ── Consolidation ─────────────────────────────────────────────────────────────

def _consolidate_text(description: str, extracted_file_text: str) -> str:
    parts = [description.strip()]
    if extracted_file_text:
        parts.append(f"[Attached content]\n{extracted_file_text.strip()}")
    return "\n\n".join(parts)
