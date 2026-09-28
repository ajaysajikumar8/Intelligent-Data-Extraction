"""
webhook_dispatcher.py — Async outbound webhook delivery engine.

Responsibilities
----------------
  1. After every document extraction completes (SUCCESS, FAILED, UNMATCHED),
     `dispatch()` is called as a fire-and-forget asyncio task so the HTTP
     response to the caller is never delayed.

  2. For each active WebhookEndpoint in the workspace that matches the
     event type and optional template filter, it:
       a. Builds the JSON payload.
       b. Signs it with HMAC-SHA256 using the endpoint's secret key, producing
          an `X-Webhook-Signature` header. Receivers verify this to confirm
          the payload came from our platform and wasn't forged.
       c. POSTs the payload with `httpx.AsyncClient` (10 s timeout).
       d. Records a `WebhookDelivery` row (status code, duration, response).
       e. Increments the endpoint's `failureCount` on non-2xx responses.
"""

import json
import logging
import time
from typing import Any

import httpx
from prisma.models import DocumentLog

from app.core.db import db
from app.core.security import hmac_sign

logger = logging.getLogger("app.services.webhook_dispatcher")

# Disable an endpoint after this many consecutive failures
AUTO_DISABLE_THRESHOLD = 10
DELIVERY_TIMEOUT_SECONDS = 10.0


async def dispatch(doc_log: DocumentLog) -> None:
    """
    Fire-and-forget entry point. Called after every extraction pipeline run.

    Finds all active WebhookEndpoints for the workspace that match the
    document's final status (event type) and optional template filter,
    then delivers to each one in parallel.
    """
    try:
        await _dispatch_all(doc_log)
    except Exception:
        logger.exception(
            "[webhook_dispatcher] Unhandled error dispatching for doc_log %s",
            doc_log.id,
        )


async def _dispatch_all(doc_log: DocumentLog) -> None:
    # Fetch all active webhook endpoints for this workspace
    endpoints = await db.webhookendpoint.find_many(
        where={"workspaceId": doc_log.workspaceId, "isActive": True},
    )

    if not endpoints:
        return

    event_type = doc_log.status  # SUCCESS | FAILED | UNMATCHED

    # Only deliver to endpoints with valid outbound event types
    if event_type not in ("SUCCESS", "FAILED", "UNMATCHED", "NEEDS_REVIEW"):
        return

    matching = []
    for endpoint in endpoints:
        # Event type filter (empty list = deliver for all events)
        event_types = endpoint.eventTypes or []
        if event_types and event_type not in event_types:
            continue

        # Template filter (empty list = deliver for all templates)
        template_ids = endpoint.templateIds or []
        if template_ids and doc_log.templateId not in template_ids:
            continue

        matching.append(endpoint)

    if not matching:
        return

    logger.info(
        "[%s] Dispatching to %d webhook endpoint(s) (event: %s)",
        doc_log.id,
        len(matching),
        event_type,
    )

    payload = _build_payload(doc_log)
    payload_bytes = json.dumps(payload).encode("utf-8")

    async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS) as client:
        for endpoint in matching:
            await _deliver(client, endpoint, doc_log, payload_bytes)


def _build_payload(doc_log: DocumentLog) -> dict[str, Any]:
    """Build the standard JSON payload we POST to customer servers."""
    base_data = {
        "documentId": doc_log.id,
        "workspaceId": doc_log.workspaceId,
        "status": doc_log.status,
    }

    if doc_log.status == "NEEDS_REVIEW":
        return {
            "event": f"extraction.{doc_log.status.lower()}",
            "data": {
                **base_data,
                "message": "Manual review required in dashboard",
            }
        }

    return {
        "event": f"extraction.{doc_log.status.lower()}",
        "data": {
            **base_data,
            "source": doc_log.source,
            "templateId": doc_log.templateId,
            "fileName": doc_log.fileName,
            "mimeType": doc_log.mimeType,
            "extractedJson": doc_log.extractedJson,
            "confidenceScores": getattr(doc_log, "confidenceScores", None),
            "validationErrors": doc_log.validationErrors,
            "processingMs": doc_log.processingMs,
            "createdAt": doc_log.createdAt.isoformat() if doc_log.createdAt else None,
        },
    }


async def _deliver(
    client: httpx.AsyncClient,
    endpoint: Any,
    doc_log: DocumentLog,
    payload_bytes: bytes,
) -> None:
    """
    Deliver payload to a single endpoint. Record delivery attempt regardless
    of success or failure. Auto-disable endpoint after threshold failures.
    """
    signature = hmac_sign(endpoint.secret, payload_bytes)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Event": f"extraction.{doc_log.status.lower()}",
        "User-Agent": "IntelligentDataExtraction-Webhook/1.0",
    }

    start = time.monotonic()
    status_code: int | None = None
    response_body: str | None = None
    error_msg: str | None = None

    try:
        response = await client.post(
            endpoint.url,
            content=payload_bytes,
            headers=headers,
        )
        status_code = response.status_code
        response_body = response.text[:2000]  # Cap at 2 KB for storage
        duration_ms = int((time.monotonic() - start) * 1000)

        if response.is_success:
            logger.info(
                "[%s] Delivered to %s — HTTP %d (%d ms)",
                doc_log.id,
                endpoint.url,
                status_code,
                duration_ms,
            )
            # Reset failure count on success
            await db.webhookendpoint.update(
                where={"id": endpoint.id},
                data={"failureCount": 0},
            )
        else:
            logger.warning(
                "[%s] Non-2xx from %s — HTTP %d",
                doc_log.id,
                endpoint.url,
                status_code,
            )
            await _increment_failure(endpoint)

    except httpx.TimeoutException:
        error_msg = f"Request timed out after {DELIVERY_TIMEOUT_SECONDS}s"
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning("[%s] Timeout delivering to %s", doc_log.id, endpoint.url)
        await _increment_failure(endpoint)

    except Exception as exc:
        error_msg = str(exc)[:500]
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.exception("[%s] Error delivering to %s: %s", doc_log.id, endpoint.url, exc)
        await _increment_failure(endpoint)

    finally:
        # Always record the delivery attempt
        await db.webhookdelivery.create(
            data={
                "webhook": {"connect": {"id": endpoint.id}},
                "documentLog": {"connect": {"id": doc_log.id}},
                "statusCode": status_code,
                "responseBody": response_body,
                "durationMs": duration_ms if "duration_ms" in dir() else None,  # type: ignore[name-defined]
                "error": error_msg,
            }  # type: ignore[arg-type]
        )


async def _increment_failure(endpoint: Any) -> None:
    """Increment failure count and auto-disable endpoint at threshold."""
    new_count = (endpoint.failureCount or 0) + 1
    update_data: dict[str, Any] = {"failureCount": new_count}
    if new_count >= AUTO_DISABLE_THRESHOLD:
        update_data["isActive"] = False
        logger.warning(
            "WebhookEndpoint %s auto-disabled after %d consecutive failures.",
            endpoint.id,
            new_count,
        )
    await db.webhookendpoint.update(where={"id": endpoint.id}, data=update_data)
