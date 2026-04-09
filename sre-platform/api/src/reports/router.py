"""Reports router — accepts incident description + image upload."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Form, UploadFile

from src.auth.dependencies import get_current_user

logger = structlog.get_logger()
router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/", status_code=201)
async def create_report(
    description: Annotated[str, Form()],
    image: Annotated[UploadFile, File()],
    current_user: str = Depends(get_current_user),
) -> dict:
    """
    Accept an incident report with a text description and a single image.
    The report is acknowledged and logged; persistence is handled later.
    """
    report_id = str(uuid.uuid4())
    image_filename = image.filename
    image_content_type = image.content_type

    logger.info(
        "incident_report_received",
        report_id=report_id,
        submitted_by=current_user,
        image_filename=image_filename,
        image_content_type=image_content_type,
    )

    return {
        "report_id": report_id,
        "status": "received",
        "submitted_by": current_user,
        "image_filename": image_filename,
    }
