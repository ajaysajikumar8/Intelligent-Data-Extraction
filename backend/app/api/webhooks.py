"""
webhooks.py — Outbound webhook endpoint management API.

Routes
------
  POST   /api/v1/webhooks           — Register a new outbound webhook endpoint.
  GET    /api/v1/webhooks           — List all webhook endpoints for the workspace.
  GET    /api/v1/webhooks/{id}      — Get a single webhook with recent delivery history.
  PUT    /api/v1/webhooks/{id}      — Update webhook URL, filters, or active state.
  DELETE /api/v1/webhooks/{id}      — Delete webhook endpoint and all delivery history.
  POST   /api/v1/webhooks/{id}/ping — Send a test ping payload to verify delivery.

  GET    /api/v1/webhooks/inbound   — Return the workspace inbound webhook URL.
  POST   /api/v1/webhooks/inbound/rotate — Rotate the inbound secret (revokes old URL).

Authentication: Bearer JWT or X-API-Key.
"""

import json
import logging
from datetime import timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from prisma.models import Workspace

from app.core.auth import get_current_workspace
from app.core.config import get_settings
from app.core.db import db
from app.core.security import generate_inbound_secret, hmac_sign
from app.models.schemas import (
    InboundSecretResponse,
    WebhookCreate,
    WebhookDeliveryResponse,
    WebhookResponse,
    WebhookUpdate,
)

logger = logging.getLogger("app.api.webhooks")
router = APIRouter()

_PING_TIMEOUT = 10.0


# ---------------------------------------------------------------------------
# Helper — workspace isolation guard
# ---------------------------------------------------------------------------

async def _get_webhook_or_404(webhook_id: str, workspace_id: str):
    wh = await db.webhookendpoint.find_first(
        where={"id": webhook_id, "workspaceId": workspace_id},
    )
    if not wh:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found.")
    return wh


# ---------------------------------------------------------------------------
# Inbound URL management (placed before /{id} routes to avoid path conflicts)
# ---------------------------------------------------------------------------

@router.get("/inbound", response_model=InboundSecretResponse)
async def get_inbound_url(
    workspace: Workspace = Depends(get_current_workspace),
) -> InboundSecretResponse:
    """
    Return the workspace's inbound webhook URL.
    The customer pastes this URL into SendGrid, Mailgun, Zapier, etc.
    """
    settings = get_settings()
    base = settings.API_BASE_URL.rstrip("/")
    return InboundSecretResponse(
        inboundSecret=workspace.inboundSecret,  # type: ignore[arg-type]
        inboundUrl=f"{base}/api/v1/inbound/{workspace.inboundSecret}",
    )


@router.post(
    "/inbound/rotate",
    response_model=InboundSecretResponse,
    status_code=status.HTTP_200_OK,
)
async def rotate_inbound_secret(
    workspace: Workspace = Depends(get_current_workspace),
) -> InboundSecretResponse:
    """
    Rotate the inbound webhook secret. Immediately revokes the old URL.
    The customer must update their integration with the new URL.
    """
    new_secret = generate_inbound_secret()
    updated = await db.workspace.update(
        where={"id": workspace.id},
        data={"inboundSecret": new_secret},
    )
    settings = get_settings()
    base = settings.API_BASE_URL.rstrip("/")
    logger.info("Inbound secret rotated for workspace %s", workspace.id)
    return InboundSecretResponse(
        inboundSecret=updated.inboundSecret,  # type: ignore[arg-type]
        inboundUrl=f"{base}/api/v1/inbound/{updated.inboundSecret}",
        message="Inbound secret rotated. Update your integration with the new URL.",
    )


# ---------------------------------------------------------------------------
# Outbound CRUD
# ---------------------------------------------------------------------------

@router.post("/", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    payload: WebhookCreate,
    workspace: Workspace = Depends(get_current_workspace),
) -> WebhookResponse:
    """
    Register a new outbound webhook endpoint for this workspace.
    A unique HMAC secret is auto-generated — customers use it to verify
    incoming payloads by re-computing `X-Webhook-Signature`.
    """
    import secrets

    # Plan quota check
    plan = await db.plan.find_unique(where={"id": workspace.planId})
    if plan and plan.maxWebhooks is not None:
        current_count = await db.webhookendpoint.count(
            where={"workspaceId": workspace.id}
        )
        if current_count >= plan.maxWebhooks:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Webhook limit of {plan.maxWebhooks} reached for plan '{plan.name}'.",
            )

    wh = await db.webhookendpoint.create(
        data={
            "workspace": {"connect": {"id": workspace.id}},
            "url": str(payload.url),
            "secret": secrets.token_hex(32),
            "description": payload.description,
            "eventTypes": [e.value for e in (payload.eventTypes or [])],
            "templateIds": payload.templateIds or [],
        }  # type: ignore[arg-type]
    )
    return WebhookResponse.model_validate(wh)


@router.get("/", response_model=list[WebhookResponse])
async def list_webhooks(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[WebhookResponse]:
    """List all outbound webhook endpoints for the workspace."""
    webhooks = await db.webhookendpoint.find_many(
        where={"workspaceId": workspace.id},
        skip=skip,
        take=limit,
        order={"createdAt": "desc"},
    )
    return [WebhookResponse.model_validate(w) for w in webhooks]


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: str,
    workspace: Workspace = Depends(get_current_workspace),
) -> WebhookResponse:
    """Get a single webhook endpoint by ID."""
    wh = await _get_webhook_or_404(webhook_id, workspace.id)
    return WebhookResponse.model_validate(wh)


@router.put("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: str,
    payload: WebhookUpdate,
    workspace: Workspace = Depends(get_current_workspace),
) -> WebhookResponse:
    """Update a webhook's URL, description, event/template filters, or active state."""
    await _get_webhook_or_404(webhook_id, workspace.id)

    update_data: dict = {}
    if payload.url is not None:
        update_data["url"] = str(payload.url)
    if payload.description is not None:
        update_data["description"] = payload.description
    if payload.eventTypes is not None:
        update_data["eventTypes"] = [e.value for e in payload.eventTypes]
    if payload.templateIds is not None:
        update_data["templateIds"] = payload.templateIds
    if payload.isActive is not None:
        update_data["isActive"] = payload.isActive
        if payload.isActive:
            # Re-enabling resets the failure counter
            update_data["failureCount"] = 0

    updated = await db.webhookendpoint.update(
        where={"id": webhook_id},
        data=update_data,  # type: ignore[arg-type]
    )
    return WebhookResponse.model_validate(updated)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    workspace: Workspace = Depends(get_current_workspace),
) -> None:
    """Delete a webhook endpoint and all its delivery history records."""
    await _get_webhook_or_404(webhook_id, workspace.id)
    # Delete delivery records first (FK constraint)
    await db.webhookdelivery.delete_many(where={"webhookId": webhook_id})
    await db.webhookendpoint.delete(where={"id": webhook_id})
    logger.info("Webhook %s deleted from workspace %s", webhook_id, workspace.id)


# ---------------------------------------------------------------------------
# Ping / Test
# ---------------------------------------------------------------------------

@router.post("/{webhook_id}/ping", status_code=status.HTTP_200_OK)
async def ping_webhook(
    webhook_id: str,
    workspace: Workspace = Depends(get_current_workspace),
) -> dict:
    """
    Send a test ping payload to the webhook URL.
    Returns the HTTP status code and response from the customer's server.
    Updates lastPingAt on the endpoint record.
    """
    wh = await _get_webhook_or_404(webhook_id, workspace.id)

    ping_payload = {
        "event": "ping",
        "data": {
            "workspaceId": workspace.id,
            "webhookId": wh.id,
            "message": "Ping from Intelligent Data Extraction — webhook is configured correctly!",
        },
    }
    payload_bytes = json.dumps(ping_payload).encode("utf-8")
    signature = hmac_sign(wh.secret, payload_bytes)

    try:
        async with httpx.AsyncClient(timeout=_PING_TIMEOUT) as client:
            response = await client.post(
                wh.url,
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": f"sha256={signature}",
                    "X-Webhook-Event": "ping",
                    "User-Agent": "IntelligentDataExtraction-Webhook/1.0",
                },
            )
        status_code = response.status_code
        response_body = response.text[:500]
        success = response.is_success
    except httpx.RequestError as exc:
        status_code = None
        response_body = str(exc)
        success = False

    # Update lastPingAt
    from datetime import datetime
    await db.webhookendpoint.update(
        where={"id": wh.id},
        data={"lastPingAt": datetime.now(timezone.utc)},  # type: ignore[arg-type]
    )

    return {
        "success": success,
        "statusCode": status_code,
        "responseBody": response_body,
        "webhookId": wh.id,
        "url": wh.url,
    }


# ---------------------------------------------------------------------------
# Delivery history for a specific webhook
# ---------------------------------------------------------------------------

@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_webhook_deliveries(
    webhook_id: str,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Max records to return"),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[WebhookDeliveryResponse]:
    """Return the recent delivery attempts for a specific outbound webhook."""
    await _get_webhook_or_404(webhook_id, workspace.id)
    deliveries = await db.webhookdelivery.find_many(
        where={"webhookId": webhook_id},
        skip=skip,
        take=limit,
        order={"createdAt": "desc"},
    )
    return [WebhookDeliveryResponse.model_validate(d) for d in deliveries]
