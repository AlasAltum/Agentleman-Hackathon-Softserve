"""Reports router — forwards incident reports to the backend ingest API."""

from typing import Annotated, Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from src.auth.dependencies import get_current_user
from src.config import BACKEND_URL

logger = structlog.get_logger()
router = APIRouter(prefix="/reports", tags=["reports"])

_INGEST_URL = f"{BACKEND_URL}/api/ingest"
_FORWARD_TIMEOUT = 120.0


@router.post("/", status_code=202)
async def create_report(
    description: Annotated[str, Form()],
    image: Annotated[UploadFile, File()],
    logs: Annotated[Optional[UploadFile], File()] = None,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Accept an incident report and forward it to the backend ingest endpoint."""

    logger.info(
        "forwarding_report",
        submitted_by=current_user,
        image_filename=image.filename,
        has_logs=logs is not None,
    )

    image_bytes = await image.read()
    files = [
        ("file_attachments", (image.filename, image_bytes, image.content_type or "application/octet-stream")),
    ]
    if logs is not None:
        logs_bytes = await logs.read()
        files.append(
            ("file_attachments", (logs.filename, logs_bytes, logs.content_type or "application/octet-stream")),
        )

    data = {
        "text_desc": description,
        "reporter_email": current_user,
    }

    try:
        async with httpx.AsyncClient(timeout=_FORWARD_TIMEOUT) as client:
            resp = await client.post(_INGEST_URL, data=data, files=files)
    except httpx.RequestError as exc:
        logger.error("backend_unreachable", url=_INGEST_URL, error=str(exc))
        raise HTTPException(status_code=502, detail="Backend service is unreachable.")

    if resp.status_code >= 400:
        logger.warning("backend_rejected", status=resp.status_code, body=resp.text[:500])
        raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail", "Backend rejected the report."))

    result = resp.json()
    logger.info("report_accepted", request_id=result.get("request_id"))
    return result
