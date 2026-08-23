"""
ingest.py — Dual-mode document ingestion endpoint.

POST /api/v1/ingest accepts two content modes:
  • JSON mode      — Content-Type: application/json
                     Body: {"rawInput": "text...", "source": "MANUAL"|"API"}
  • Multipart mode — Content-Type: multipart/form-data
                     Fields: file (UploadFile), source (optional)

Both modes:
  1. Create a DocumentLog record at status=PENDING.
  2. Check monthly extraction quota against the workspace's Plan.
  3. Delegate to the extraction_pipeline, which updates the record
     through PROCESSING → SUCCESS | FAILED | UNMATCHED.
  4. Return the final DocumentLog as the response.

Authentication: Bearer JWT (dashboard users) or X-API-Key (integrations).
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from prisma.models import User, Workspace

from app.core.auth import get_current_user, get_current_workspace
from app.core.db import db
from app.models.schemas import DocumentLogResponse, Source
from app.services import extraction_pipeline

logger = logging.getLogger("app.api.ingest")
router = APIRouter()

# Allowed MIME types for file uploads
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
}

# Max file size: 20 MB (Gemini inline data limit)
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024


# ---------------------------------------------------------------------------
# Quota check helper
# ---------------------------------------------------------------------------

async def _check_quota(workspace: Workspace) -> None:
    """
    Verify the workspace has not exceeded its monthly extraction quota.
    Raises HTTP 429 if the limit is reached.
    """
    plan = await db.plan.find_unique(where={"id": workspace.planId})
    if not plan or plan.maxExtractionsPerMonth is None:
        return  # Unlimited

    now = datetime.now(timezone.utc)
    start_of_month = now.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    count = await db.documentlog.count(
        where={
            "workspaceId": workspace.id,
            "createdAt": {"gte": start_of_month},
        }
    )

    if count >= plan.maxExtractionsPerMonth:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Monthly extraction quota of {plan.maxExtractionsPerMonth} "
                f"reached for plan '{plan.name}'. Upgrade your plan to continue."
            ),
        )


# ---------------------------------------------------------------------------
# POST /ingest — JSON mode
# ---------------------------------------------------------------------------

@router.post("/json", response_model=DocumentLogResponse, status_code=status.HTTP_201_CREATED)
async def ingest_json(
    raw_input: str,
    source: Source = Source.MANUAL,
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User | None = Depends(get_current_user),
) -> DocumentLogResponse:
    """
    JSON-mode ingestion endpoint.

    Accepts a plain text body (email body, document text, structured notes)
    and runs it through the full AI extraction pipeline.

    The `source` field defaults to `MANUAL` (dashboard paste) but can be
    set to `API` for programmatic callers.
    """
    if not raw_input or not raw_input.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rawInput must not be empty.",
        )

    await _check_quota(workspace)

    # Create the DocumentLog record at PENDING
    create_data: dict = {
        "workspace": {"connect": {"id": workspace.id}},
        "source": source.value,  # type: ignore[arg-type]
        "status": "PENDING",
        "rawInput": raw_input,
    }
    if current_user:
        create_data["user"] = {"connect": {"id": current_user.id}}

    doc_log = await db.documentlog.create(data=create_data)  # type: ignore[arg-type]

    logger.info(
        "Ingest (JSON) started — doc_log: %s, workspace: %s", doc_log.id, workspace.id
    )

    # Run pipeline (updates doc_log in-place)
    final_log = await extraction_pipeline.run(
        doc_log_id=doc_log.id,
        workspace_id=workspace.id,
        raw_text=raw_input,
    )

    return DocumentLogResponse.model_validate(final_log)


# ---------------------------------------------------------------------------
# POST /ingest — Multipart/file mode
# ---------------------------------------------------------------------------

@router.post("/file", response_model=DocumentLogResponse, status_code=status.HTTP_201_CREATED)
async def ingest_file(
    file: UploadFile = File(...),
    source: Source = Form(Source.MANUAL),
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User | None = Depends(get_current_user),
) -> DocumentLogResponse:
    """
    File-mode ingestion endpoint.

    Accepts a PDF, PNG, or JPEG upload and runs it through the full AI
    extraction pipeline. The file is passed as inline base64 data to Gemini
    (no external object storage required for files under 20 MB).
    """
    # Validate MIME type
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{content_type}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
            ),
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    await _check_quota(workspace)

    file_create_data: dict = {
        "workspace": {"connect": {"id": workspace.id}},
        "source": source.value,  # type: ignore[arg-type]
        "status": "PENDING",
        "fileName": file.filename,
        "mimeType": content_type,
    }
    if current_user:
        file_create_data["user"] = {"connect": {"id": current_user.id}}

    doc_log = await db.documentlog.create(data=file_create_data)  # type: ignore[arg-type]

    logger.info(
        "Ingest (file) started — doc_log: %s, file: %s, workspace: %s",
        doc_log.id,
        file.filename,
        workspace.id,
    )

    final_log = await extraction_pipeline.run(
        doc_log_id=doc_log.id,
        workspace_id=workspace.id,
        file_bytes=file_bytes,
        mime_type=content_type,
    )

    return DocumentLogResponse.model_validate(final_log)
