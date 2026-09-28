"""
test_inbound.py — Tests for the universal inbound webhook adapter.

All providers (SendGrid, Mailgun, Make.com, generic) now route through the
single POST /api/v1/inbound/{inbound_secret} endpoint.
"""

import io
import pytest
from unittest.mock import patch
from uuid import uuid4
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.schemas import InboundResponse

MOCK_RESPONSE = InboundResponse(message="Accepted for processing", document_log_id="doc-123")


async def _signup(client: AsyncClient) -> str:
    """Sign up a new workspace and return its inbound secret."""
    email = f"inbound_{uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "workspaceName": "Inbound WS"},
    )
    assert res.status_code == 201
    return res.json()["workspace"]["inboundSecret"]


# ---------------------------------------------------------------------------
# Core acceptance tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generic_inbound_text_only():
    """Plain text payload via rawInput field."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        secret = await _signup(client)
        with patch("app.api.inbound._run_pipeline", return_value=MOCK_RESPONSE) as mock:
            res = await client.post(
                f"/api/v1/inbound/{secret}",
                data={"rawInput": "Hello from generic webhook", "templateId": "tpl-123"},
            )
        assert res.status_code == 202
        assert res.json()["message"] == "Accepted for processing"
        _, kwargs = mock.call_args
        assert kwargs["raw_text"] == "Hello from generic webhook"
        assert kwargs["template_id"] == "tpl-123"
        assert kwargs["source"].value == "WEBHOOK"


@pytest.mark.asyncio
async def test_invalid_secret_returns_404():
    """Unknown inbound secret must return 404, not 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/inbound/totally_invalid_secret_xyz",
            data={"rawInput": "Hello"},
        )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_no_payload_returns_422():
    """Posting with neither text nor file must be rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        secret = await _signup(client)
        res = await client.post(f"/api/v1/inbound/{secret}", data={})
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Provider alias coverage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sendgrid_field_aliases():
    """SendGrid sends 'text' and 'subject' — should be normalised to EMAIL source."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        secret = await _signup(client)
        with patch("app.api.inbound._run_pipeline", return_value=MOCK_RESPONSE) as mock:
            res = await client.post(
                f"/api/v1/inbound/{secret}",
                data={"text": "Invoice attached", "subject": "Invoice #1234"},
            )
        assert res.status_code == 202
        _, kwargs = mock.call_args
        # Subject should be prepended to body
        assert "Subject: Invoice #1234" in kwargs["raw_text"]
        assert "Invoice attached" in kwargs["raw_text"]
        # Email signals (subject) → source=EMAIL
        assert kwargs["source"].value == "EMAIL"


@pytest.mark.asyncio
async def test_mailgun_field_aliases():
    """Mailgun uses 'body-plain' — should map to raw_text."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        secret = await _signup(client)
        with patch("app.api.inbound._run_pipeline", return_value=MOCK_RESPONSE) as mock:
            res = await client.post(
                f"/api/v1/inbound/{secret}",
                # httpx sends body-plain as form field
                data={"body-plain": "Hello from Mailgun"},
            )
        assert res.status_code == 202
        _, kwargs = mock.call_args
        assert kwargs["raw_text"] == "Hello from Mailgun"
        # body-plain is an email signal → source=EMAIL
        assert kwargs["source"].value == "EMAIL"


@pytest.mark.asyncio
async def test_subject_only_becomes_resolved_text():
    """Subject alone (no body) should still produce resolved_text."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        secret = await _signup(client)
        with patch("app.api.inbound._run_pipeline", return_value=MOCK_RESPONSE) as mock:
            res = await client.post(
                f"/api/v1/inbound/{secret}",
                data={"subject": "Restock Request"},
            )
        assert res.status_code == 202
        _, kwargs = mock.call_args
        assert kwargs["raw_text"] == "Subject: Restock Request"
        assert kwargs["source"].value == "EMAIL"


# ---------------------------------------------------------------------------
# File handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_file_with_unsupported_mime_is_skipped_when_text_present():
    """
    An unsupported MIME attachment (e.g. .p7s email signature) should be
    silently skipped. The request should still succeed if text is present.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        secret = await _signup(client)
        with patch("app.api.inbound._run_pipeline", return_value=MOCK_RESPONSE) as mock:
            res = await client.post(
                f"/api/v1/inbound/{secret}",
                data={"text": "Email body text"},
                files={"attachment1": ("smime.p7s", io.BytesIO(b"fake-sig"), "application/pkcs7-signature")},
            )
        assert res.status_code == 202
        _, kwargs = mock.call_args
        # File should have been skipped — only text reaches the pipeline
        assert kwargs["raw_text"] == "Email body text"
        assert kwargs["file_bytes"] is None


@pytest.mark.asyncio
async def test_attachment2_is_supported():
    """SendGrid can send up to attachment2 — both fields should be tried."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        secret = await _signup(client)
        # attachment1 = unsupported, attachment2 = valid PDF
        fake_pdf = b"%PDF-1.4 fake pdf content"
        with patch("app.api.inbound._run_pipeline", return_value=MOCK_RESPONSE) as mock:
            res = await client.post(
                f"/api/v1/inbound/{secret}",
                data={"text": "See attached PDF"},
                files={
                    "attachment1": ("smime.p7s", io.BytesIO(b"sig"), "application/pkcs7-signature"),
                    "attachment2": ("invoice.pdf", io.BytesIO(fake_pdf), "application/pdf"),
                },
            )
        assert res.status_code == 202
        _, kwargs = mock.call_args
        # attachment1 skipped (bad MIME), attachment2 accepted
        assert kwargs["file_bytes"] == fake_pdf
        assert kwargs["mime_type"] == "application/pdf"
        assert kwargs["file_name"] == "invoice.pdf"


# ---------------------------------------------------------------------------
# The old /sendgrid/ path no longer exists
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sendgrid_specific_route_is_gone():
    """
    The /inbound/sendgrid/{secret} route has been removed.
    All SendGrid traffic should use /inbound/{secret} directly.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        secret = await _signup(client)
        res = await client.post(
            f"/api/v1/inbound/sendgrid/{secret}",
            data={"text": "This should 404"},
        )
    # sendgrid/ is no longer a registered route — FastAPI returns 404 or 405
    assert res.status_code in (404, 405)
