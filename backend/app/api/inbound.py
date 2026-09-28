"""
inbound.py — Inbound webhook adapter routes.

These are NOT new extraction pipelines. They are lightweight adapters
(translators) that convert third-party payload formats into the standard
rawInput + file format, then delegate directly to the extraction pipeline.

The workspace is identified by the `inbound_secret` path parameter — a
cryptographically unguessable 256-bit hex token embedded in the URL.
No X-API-Key header is needed (third-party platforms cannot add custom headers).

Route
-----
  POST /api/v1/inbound/{inbound_secret}
       Universal inbound adapter. Accepts a flexible payload with all common
       field name aliases used by every major provider:

       Text aliases  : rawInput, text (SendGrid / custom), body-plain (Mailgun),
                       body (Make.com), content (Typeform), html (email parsers),
                       subject (email subject line)
       File aliases  : file, attachment, attachment1 (SendGrid), attachment-1
                       (Mailgun), attachment2 (SendGrid multi-attach)
       Optional      : templateId

       The adapter normalises all of these into a single (raw_text, file_bytes)
       pair and hands off to the extraction pipeline.

Previously there was a separate /sendgrid/{inbound_secret} route. It has been
removed — the generic adapter already handles all SendGrid field names natively.
Unsupported MIME attachments (e.g. email signature .p7s files) are silently
skipped and a warning is logged, matching the previous SendGrid-specific
behaviour.

Security model
--------------
  1. The `inbound_secret` is a 64-character hex string (256-bit entropy)
     unique per workspace and embedded in the URL path.

  2. Returns 404 (not 401) on unknown secret — no info leakage.

  3. The secret is rotatable from Settings → Webhooks → Rotate Inbound URL.

All inbound routes respond immediately with HTTP 202 Accepted and delegate
extraction to the pipeline asynchronously — this prevents third-party services
from timing out while Gemini processes the document.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.core.db import db
from app.core.utils import validate_and_read_file
from app.models.schemas import InboundResponse, Source
from app.services import extraction_pipeline

logger = logging.getLogger("app.api.inbound")
router = APIRouter()


# ---------------------------------------------------------------------------
# Common: resolve workspace from inbound_secret path parameter
# ---------------------------------------------------------------------------

async def _resolve_workspace(inbound_secret: str):
    """
    Resolve the workspace from the inbound_secret URL token.
    The secret replaces the need for an X-API-Key header — useful for
    third-party integrations that cannot set custom request headers.
    """
    workspace = await db.workspace.find_unique(
        where={"inboundSecret": inbound_secret},
        include={"plan": True},
    )
    if not workspace:
        # Return 404 (not 401) — no information leakage about valid secrets
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inbound webhook URL not found. Check your configuration.",
        )
    return workspace


async def _resolve_file(
    candidates: list[Optional[UploadFile]],
) -> tuple[bytes | None, str | None, str | None]:
    """
    Try each candidate UploadFile in order and return (file_bytes, mime_type,
    file_name) for the first one that passes validation.

    Unsupported MIME types (e.g. email signature .p7s files sent by SendGrid)
    are silently skipped with a warning. Any other error (e.g. file too large)
    is re-raised immediately.
    """
    for upload in candidates:
        if upload is None:
            continue
        try:
            file_bytes, mime_type = await validate_and_read_file(upload)
            return file_bytes, mime_type, upload.filename
        except HTTPException as exc:
            if exc.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE:
                logger.warning(
                    "Skipping unsupported attachment '%s' (%s)",
                    upload.filename,
                    exc.detail,
                )
                continue  # try next candidate
            raise  # re-raise 413 (too large) and anything unexpected

    return None, None, None


async def _run_pipeline(
    workspace,
    raw_text: str | None,
    file_bytes: bytes | None,
    mime_type: str | None,
    file_name: str | None,
    source: Source,
    template_id: str | None,
) -> InboundResponse:
    """
    Create a DocumentLog record and kick off the extraction pipeline.
    Called by every inbound adapter after translating the payload.
    """
    has_text = bool(raw_text and raw_text.strip())
    has_file = file_bytes is not None

    create_data: dict = {
        "workspace": {"connect": {"id": workspace.id}},
        "source": source.value,
        "status": "PENDING",
    }
    if has_text:
        create_data["rawInput"] = raw_text.strip()  # type: ignore[union-attr]
    if has_file:
        create_data["fileName"] = file_name
        create_data["mimeType"] = mime_type

    doc_log = await db.documentlog.create(data=create_data)  # type: ignore[arg-type]

    # Fire pipeline as asyncio background task — respond immediately
    asyncio.create_task(
        extraction_pipeline.run(
            doc_log_id=doc_log.id,
            workspace_id=workspace.id,
            raw_text=raw_text.strip() if has_text else None,
            file_bytes=file_bytes,
            mime_type=mime_type,
            target_template_id=template_id,
        )
    )

    return InboundResponse(
        message="Accepted for processing",
        document_log_id=doc_log.id,
    )


# ---------------------------------------------------------------------------
# Universal inbound adapter
# Supports: Zapier, Make.com, n8n, Typeform, SendGrid, Mailgun, Postmark,
#           AWS SES, custom webhooks — anything that sends multipart/form-data
#           or application/x-www-form-urlencoded.
# ---------------------------------------------------------------------------

@router.post(
    "/{inbound_secret}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=InboundResponse,
    summary="Universal Inbound Webhook",
    description=(
        "Universal adapter accepting documents & emails from any third-party tool or provider "
        "(Zapier, Make.com, SendGrid, Mailgun, Postmark, AWS SES, custom webhooks, n8n, Typeform). "
        "Normalizes text/email bodies, subject lines, and file attachments automatically. "
        "To add support for a new provider, simply map their field names to one of the "
        "recognised aliases below — no new endpoint needed."
    ),
)
async def generic_inbound(
    inbound_secret: str,
    # ── Text field aliases ────────────────────────────────────────────────
    raw_input:  Optional[str] = Form(None, alias="rawInput"),  # Our native field
    text:       Optional[str] = Form(None),                    # SendGrid, Postmark, custom
    body:       Optional[str] = Form(None),                    # Make.com, custom
    body_plain: Optional[str] = Form(None, alias="body-plain"),# Mailgun
    content:    Optional[str] = Form(None),                    # Typeform, custom
    html:       Optional[str] = Form(None),                    # Email parsers (fallback)
    subject:    Optional[str] = Form(None),                    # Email subject line
    # ── File field aliases ────────────────────────────────────────────────
    file:         Optional[UploadFile] = File(None),                        # Generic
    attachment:   Optional[UploadFile] = File(None),                        # Generic
    attachment1:  Optional[UploadFile] = File(None),                        # SendGrid
    attachment_1: Optional[UploadFile] = File(None, alias="attachment-1"),  # Mailgun
    attachment2:  Optional[UploadFile] = File(None),                        # SendGrid (2nd)
    # ── Routing ──────────────────────────────────────────────────────────
    template_id: Optional[str] = Form(None, alias="templateId"),
) -> InboundResponse:
    workspace = await _resolve_workspace(inbound_secret)

    # ── Resolve text: first non-empty alias wins ──────────────────────────
    raw_body = raw_input or text or body_plain or body or content or html

    # Prepend subject line when present — gives the AI useful context
    if subject and raw_body:
        resolved_text: str | None = f"Subject: {subject}\n\n{raw_body}"
    elif subject:
        resolved_text = f"Subject: {subject}"
    else:
        resolved_text = raw_body

    # ── Resolve file: first valid attachment wins; skip unsupported MIMEs ─
    file_bytes, mime_type, file_name = await _resolve_file([
        file, attachment, attachment1, attachment_1, attachment2
    ])

    if not resolved_text and file_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of rawInput/body or file/attachment must be provided.",
        )

    # ── Auto-detect source channel from email payload signals ─────────────
    is_email = bool(subject or body_plain or attachment1 or attachment_1 or attachment2)
    source = Source.EMAIL if is_email else Source.WEBHOOK

    logger.info(
        "[inbound] workspace=%s source=%s has_text=%s has_file=%s",
        workspace.id,
        source.value,
        bool(resolved_text),
        file_bytes is not None,
    )

    return await _run_pipeline(
        workspace=workspace,
        raw_text=resolved_text,
        file_bytes=file_bytes,
        mime_type=mime_type,
        file_name=file_name,
        source=source,
        template_id=template_id,
    )
