"""
ingest.py — Document ingestion endpoint.

Routes
------
  POST /api/v1/ingest   — Single unified ingestion route.
                          Accepts any combination of:
                            • rawInput  (text)   — email body, pasted text, cover letter
                            • file      (upload) — PDF, PNG, JPEG, or WebP attachment
                          At least one must be present. When both are provided (hybrid),
                          Gemini processes both sources in a single multimodal API call.

  GET  /api/v1/ingest   — Paginated document log listing.

The source field identifies the ingestion channel:
  • MANUAL  — human user pasting/uploading via the dashboard
  • API     — developer calling with an X-API-Key
  • EMAIL   — automated email forwarding pipeline
  • WEBHOOK — inbound trigger from Zapier, Make.com, etc.

Authentication: Bearer JWT (dashboard users) or X-API-Key (integrations).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from prisma.models import User, Workspace

from app.core.auth import get_current_user, get_current_workspace
from app.core.db import db
from app.core.utils import validate_and_read_file
from app.models.schemas import DocumentLogResponse, ExtractionStatus, Source
from app.services import extraction_pipeline

logger = logging.getLogger("app.api.ingest")
router = APIRouter()


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
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

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
# GET /ingest — Paginated document log listing
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[DocumentLogResponse])
async def list_document_logs(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
    status: ExtractionStatus | None = Query(None, description="Filter by extraction status"),
    source: Source | None = Query(None, description="Filter by ingestion source"),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[DocumentLogResponse]:
    """
    Return a paginated list of DocumentLog records for the current workspace.

    Supports optional filtering by extraction status and ingestion source.
    Used by the dashboard overview and extraction logs pages.
    """
    where: dict = {"workspaceId": workspace.id}
    if status is not None:
        where["status"] = status.value
    if source is not None:
        where["source"] = source.value

    logs = await db.documentlog.find_many(
        where=where,  # type: ignore[arg-type]
        skip=skip,
        take=limit,
        order={"createdAt": "desc"},
    )

    return [DocumentLogResponse.model_validate(log) for log in logs]


# ---------------------------------------------------------------------------
# POST /ingest — Single unified ingestion endpoint
# ---------------------------------------------------------------------------

@router.post("/", response_model=DocumentLogResponse, status_code=status.HTTP_201_CREATED)
async def ingest(
    raw_input: Optional[str] = Form(None, alias="rawInput"),
    file: Optional[UploadFile] = File(None),
    source: Source = Form(Source.MANUAL),
    template_id: Optional[str] = Form(None, alias="templateId"),
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User | None = Depends(get_current_user),
) -> DocumentLogResponse:
    """
    Unified document ingestion endpoint.

    Accepts any combination of:
      • rawInput (text)   — email body, cover letter, pasted text
      • file (upload)     — PDF, PNG, JPEG, or WebP attachment

    Input modes:
      • Text-only  : rawInput set, no file.
      • File-only  : file set, no rawInput.
      • Hybrid     : BOTH set. Gemini processes both sources in a single
                     multimodal call (e.g. cover letter email + résumé PDF).

    The source field identifies the ingestion channel:
      • MANUAL  — human user on the dashboard (default)
      • API     — developer calling directly with an API key
      • EMAIL   — automated email forwarding pipeline
      • WEBHOOK — inbound trigger from Zapier, Make.com, etc.
    """
    has_text = bool(raw_input and raw_input.strip())
    has_file = file is not None

    if not has_text and not has_file:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of rawInput (text) or file must be provided.",
        )

    # Read and validate file if present
    file_bytes: bytes | None = None
    content_type: str | None = None

    if has_file:
        file_bytes, content_type = await validate_and_read_file(file)

    await _check_quota(workspace)

    # Determine mode label for logging
    if has_text and has_file:
        mode = "hybrid"
    elif has_text:
        mode = "text"
    else:
        mode = "file"

    # Build DocumentLog record
    create_data: dict = {
        "workspace": {"connect": {"id": workspace.id}},
        "source": source.value,  # type: ignore[arg-type]
        "status": "PENDING",
    }
    if has_text:
        create_data["rawInput"] = raw_input.strip()  # type: ignore[union-attr]
    if has_file:
        create_data["fileName"] = file.filename  # type: ignore[union-attr]
        create_data["mimeType"] = content_type
    if current_user:
        create_data["user"] = {"connect": {"id": current_user.id}}

    doc_log = await db.documentlog.create(data=create_data)  # type: ignore[arg-type]

    logger.info(
        "Ingest [%s/%s] started — doc_log: %s, workspace: %s",
        source.value,
        mode,
        doc_log.id,
        workspace.id,
    )

    final_log = await extraction_pipeline.run(
        doc_log_id=doc_log.id,
        workspace_id=workspace.id,
        raw_text=raw_input.strip() if has_text else None,
        file_bytes=file_bytes,
        mime_type=content_type,
        target_template_id=template_id,
    )

    return DocumentLogResponse.model_validate(final_log)
