"""
logs.py — Document extraction audit log API.

Routes
------
  GET /api/v1/logs/{document_id}
      Returns the full audit record for a single extraction:
        - raw input text / filename / MIME type
        - extracted JSON (or validation errors)
        - matched template name and version
        - processing duration
        - all outbound webhook delivery attempts (status codes, durations, errors)

Authentication: Bearer JWT or X-API-Key.
"""

import asyncio
import json as json_lib
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from prisma import Json
from prisma.models import Workspace

from typing import Any
from pydantic import BaseModel
from app.api.ingest import check_in_flight
from app.core.auth import get_current_workspace
from app.core.db import db
from app.models.schemas import DocumentLogDetailResponse, DocumentLogResponse, WebhookDeliveryResponse
from app.services import extraction_queue, failures, webhook_dispatcher
from app.services.extraction_pipeline import validate_correction

logger = logging.getLogger("app.api.logs")
router = APIRouter()

class CorrectionRequest(BaseModel):
    correctedJson: dict[str, Any]


@router.get("/{document_id}", response_model=DocumentLogDetailResponse)
async def get_document_audit_log(
    document_id: str,
    workspace: Workspace = Depends(get_current_workspace),
) -> DocumentLogDetailResponse:
    """
    Fetch the full audit trail for a single document extraction.

    Returns the DocumentLog record with:
      - All extraction fields (rawInput, fileName, extractedJson, validationErrors, etc.)
      - Associated webhook delivery attempts (outbound dispatches triggered by this extraction)

    Enforces workspace isolation — a workspace can only access its own document logs.
    """
    doc_log = await db.documentlog.find_unique(
        where={"id": document_id},
        include={"webhookDeliveries": True},
    )

    if not doc_log or doc_log.workspaceId != workspace.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document log not found.",
        )

    deliveries = [
        WebhookDeliveryResponse.model_validate(d)
        for d in (doc_log.webhookDeliveries or [])
    ]

    # Build from the model (not field by field) so new columns can never be silently dropped.
    return DocumentLogDetailResponse(
        **DocumentLogResponse.model_validate(doc_log).model_dump(),
        webhookDeliveries=deliveries,
    )

@router.post("/{document_id}/correct", response_model=DocumentLogDetailResponse)
async def correct_document_extraction(
    document_id: str,
    payload: CorrectionRequest,
    workspace: Workspace = Depends(get_current_workspace),
) -> DocumentLogDetailResponse:
    """
    Accept human corrections for a document log (usually one in NEEDS_REVIEW).
    Validates the new JSON, saves an ExtractionCorrection for future AI learning,
    updates the log to SUCCESS, and dispatches the SUCCESS webhook.
    """
    doc_log = await db.documentlog.find_unique(
        where={"id": document_id},
        include={"template": True, "webhookDeliveries": True},
    )

    if not doc_log or doc_log.workspaceId != workspace.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document log not found.",
        )

    if not doc_log.template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot correct a document that has no matched template.",
        )

    # 1. Validate the corrected JSON against the template schema
    validated_data, errors = validate_correction(doc_log.template, payload.correctedJson)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Corrected JSON violates template schema", "errors": errors},
        )

    # 2. Only a document waiting for review can be approved or corrected, and only once: the
    # status flip is the claim, so a double-click or a second reviewer cannot dispatch the
    # SUCCESS webhook twice.
    claimed = await db.documentlog.update_many(
        where={"id": doc_log.id, "workspaceId": workspace.id, "status": "NEEDS_REVIEW"},
        data={
            "status": "SUCCESS",
            "extractedJson": Json(validated_data),  # type: ignore[arg-type]
            "validationErrors": Json(None),  # type: ignore[arg-type]
        },
    )
    if not claimed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document is no longer waiting for review.",
        )

    # 3. Record the correction so later extractions on this template can learn from it.
    # Skipped when the reviewer approved the values as they are: an "original == corrected"
    # example teaches nothing and would only use up one of the few prompt slots.
    if validated_data != doc_log.extractedJson:
        await db.extractioncorrection.upsert(
            where={"documentLogId": doc_log.id},
            data={
                "create": {
                    "documentLogId": doc_log.id,
                    "templateId": doc_log.template.id,
                    "originalJson": json_lib.dumps(doc_log.extractedJson) if doc_log.extractedJson else "{}",
                    "correctedJson": json_lib.dumps(validated_data),
                    "templateVersion": doc_log.template.version,
                },
                "update": {
                    "correctedJson": json_lib.dumps(validated_data),
                    "templateVersion": doc_log.template.version,
                },
            },
        )

    updated_log = await db.documentlog.find_unique(
        where={"id": doc_log.id},
        include={"webhookDeliveries": True},
    )

    # 4. Dispatch the final SUCCESS webhook
    if updated_log:
        asyncio.create_task(webhook_dispatcher.dispatch(updated_log))

    deliveries = [
        WebhookDeliveryResponse.model_validate(d)
        for d in (updated_log.webhookDeliveries or []) # type: ignore[union-attr]
    ]

    return DocumentLogDetailResponse(
        **DocumentLogResponse.model_validate(updated_log).model_dump(),
        webhookDeliveries=deliveries,
    )


@router.post(
    "/{document_id}/retry",
    response_model=DocumentLogResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_failed_document(
    document_id: str,
    workspace: Workspace = Depends(get_current_workspace),
) -> DocumentLogResponse:
    """
    Re-queue a FAILED document that failed for a retryable reason (AI busy, rate limited,
    timeout, restart, unreadable AI output, or a missing/invalid key that was since fixed).

    The same DocumentLog is reused (reset to PENDING) rather than copied: the monthly quota
    is not charged twice and Logs does not fill with duplicates. Uploaded files are not
    stored, so only text submissions can be retried; file uploads must be submitted again.
    If the document ran on a specific/matched template, that template is reused (skipping
    classification); otherwise the retry auto-detects again.
    """
    doc_log = await db.documentlog.find_unique(where={"id": document_id})
    if not doc_log or doc_log.workspaceId != workspace.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document log not found.")

    if doc_log.status != "FAILED" or failures.failure_code(doc_log.validationErrors) not in failures.RETRYABLE_CODES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only documents that failed for a temporary reason can be retried.",
        )
    if doc_log.fileName or not (doc_log.rawInput and doc_log.rawInput.strip()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Uploaded files are not stored, so this document can't be retried. Please upload it again.",
        )

    await check_in_flight(workspace)
    try:
        extraction_queue.ensure_capacity()
    except extraction_queue.QueueFullError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The extraction service is busy right now. Please try again in a minute.",
            headers={"Retry-After": "30"},
        )

    # Claim the retry atomically so a double-click or two tabs cannot queue the job twice.
    # createdAt is reset: it is the "queued at" time that crash recovery and the in-flight cap use.
    claimed = await db.documentlog.update_many(
        where={"id": doc_log.id, "workspaceId": workspace.id, "status": "FAILED"},
        data={
            "status": "PENDING",
            "validationErrors": Json(None),  # type: ignore[arg-type]
            "progress": Json(None),  # type: ignore[arg-type]
            "processingMs": None,
            "apiKeySource": None,  # re-decided when the retry runs
            "modelUsed": None,
            "createdAt": datetime.now(timezone.utc),
        },
    )
    if not claimed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This document is already being retried.")

    logger.info("Retrying document %s (workspace %s)", doc_log.id, workspace.id)
    extraction_queue.enqueue(
        doc_log_id=doc_log.id,
        workspace=workspace,
        raw_text=doc_log.rawInput.strip(),
        file_bytes=None,
        mime_type=None,
        template_id=doc_log.templateId,
    )

    refreshed = await db.documentlog.find_unique(where={"id": doc_log.id})
    return DocumentLogResponse.model_validate(refreshed)
