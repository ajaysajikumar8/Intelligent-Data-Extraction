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

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from prisma.models import Workspace

from typing import Any
from pydantic import BaseModel
from app.core.auth import get_current_workspace
from app.core.db import db
from app.models.schemas import DocumentLogDetailResponse, WebhookDeliveryResponse
from app.services import webhook_dispatcher
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

    return DocumentLogDetailResponse(
        id=doc_log.id,
        workspaceId=doc_log.workspaceId,
        templateId=doc_log.templateId,
        userId=doc_log.userId,
        source=doc_log.source,  # type: ignore[arg-type]
        status=doc_log.status,  # type: ignore[arg-type]
        rawInput=doc_log.rawInput,
        rawInputUrl=doc_log.rawInputUrl,
        fileName=doc_log.fileName,
        mimeType=doc_log.mimeType,
        extractedJson=doc_log.extractedJson,
        validationErrors=doc_log.validationErrors,
        processingMs=doc_log.processingMs,
        createdAt=doc_log.createdAt,
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

    # 2. Record the correction for prompt injection
    # Upsert in case it was corrected multiple times (one correction per document)
    import json as json_lib
    
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
            }
        }
    )

    # 3. Update the DocumentLog
    import time
    import asyncio
    from prisma import Json

    updated_log = await db.documentlog.update(
        where={"id": doc_log.id},
        data={
            "status": "SUCCESS",
            "extractedJson": Json(validated_data), # type: ignore[arg-type]
            "validationErrors": None,
        },
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
        id=updated_log.id, # type: ignore[union-attr]
        workspaceId=updated_log.workspaceId, # type: ignore[union-attr]
        templateId=updated_log.templateId, # type: ignore[union-attr]
        userId=updated_log.userId, # type: ignore[union-attr]
        source=updated_log.source,  # type: ignore[arg-type]
        status=updated_log.status,  # type: ignore[arg-type]
        rawInput=updated_log.rawInput, # type: ignore[union-attr]
        rawInputUrl=updated_log.rawInputUrl, # type: ignore[union-attr]
        fileName=updated_log.fileName, # type: ignore[union-attr]
        mimeType=updated_log.mimeType, # type: ignore[union-attr]
        extractedJson=updated_log.extractedJson, # type: ignore[union-attr]
        validationErrors=updated_log.validationErrors, # type: ignore[union-attr]
        processingMs=updated_log.processingMs, # type: ignore[union-attr]
        createdAt=updated_log.createdAt, # type: ignore[union-attr]
        webhookDeliveries=deliveries,
    )
