"""
test_ingest.py — Ingestion pipeline tests with Gemini mocked.

We patch `app.services.gemini_service.generate_text` so tests run without
a real Gemini API key and without network calls, while still exercising the
full pipeline logic — quota checking, DocumentLog lifecycle, Stage 1 classify,
Stage 2 extract, Stage 3 validate.

All tests hit POST /api/v1/ingest/ — the single unified endpoint.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from httpx import ASGITransport, AsyncClient

from app.core.db import db
from app.main import app
from app.services import extraction_queue


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

async def _signup_and_create_template(client: AsyncClient) -> tuple[str, str, str, str, str]:
    """
    Create a workspace via signup, then create an Invoice template.
    Returns (token, api_key, workspace_id, user_id, template_id).
    """
    email = f"ingest_{uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "Password123!",
            "workspaceName": "Ingest Test WS",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    token = data["access_token"]
    api_key = data["workspace"]["apiKey"]
    workspace_id = data["workspace"]["id"]
    user_id = data["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # These tests exercise the extraction pipeline itself (classify/extract/
    # validate), not the BYOAK key-gating logic, so opt this workspace into
    # platform-key usage directly rather than via the paid-plan-gated endpoint.
    await db.workspace.update(
        where={"id": workspace_id},
        data={"allowPlatformFallback": True},
    )

    tmpl_res = await client.post(
        "/api/v1/templates",
        json={
            "name": "Invoice Template",
            "description": "Extracts invoice data from emails or PDFs.",
            "schema": {
                "vendor_name": "string",
                "invoice_number": "string",
                "total_amount": "number",
            },
        },
        headers=headers,
    )
    assert tmpl_res.status_code == 201, tmpl_res.text
    template_id = tmpl_res.json()["id"]

    return token, api_key, workspace_id, user_id, template_id


async def _ingest_and_wait(client: AsyncClient, headers: dict, form: dict) -> dict:
    """
    POST to the ingest endpoint, assert the 202/PENDING contract, wait for the
    background job to finish, and return the final DocumentLog JSON.

    Must be called *inside* any `patch(...)` block: the pipeline runs after the
    response is returned, so the patch has to outlive the request.
    """
    res = await client.post("/api/v1/ingest/", data=form, headers=headers)
    assert res.status_code == 202, res.text
    assert res.json()["status"] == "PENDING"
    await extraction_queue.wait_idle()
    final = await client.get(f"/api/v1/logs/{res.json()['id']}", headers=headers)
    assert final.status_code == 200, final.text
    return final.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_text_success():
    """
    Full text-only pipeline with mocked Gemini:
    - Stage 1 returns the correct template ID (classification)
    - Stage 2 returns a valid JSON blob (extraction)
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, _, workspace_id, user_id, template_id = (
            await _signup_and_create_template(client)
        )
        headers = {"Authorization": f"Bearer {token}"}

        extracted_payload = json.dumps({
            "vendor_name": "Acme Corp",
            "invoice_number": "INV-2024-001",
            "total_amount": 1234.56,
        })

        # Patch generate_text: first call returns the template ID (classify),
        # second call returns the JSON extraction result.
        with patch(
            "app.services.gemini_service.generate_text",
            new=AsyncMock(side_effect=[template_id, extracted_payload]),
        ):
            data = await _ingest_and_wait(
                client,
                headers,
                {"rawInput": "Please process this invoice from Acme Corp, INV-2024-001, total $1234.56"},
            )

        assert data["status"] == "SUCCESS"
        assert data["workspaceId"] == workspace_id
        assert data["templateId"] == template_id
        assert data["processingMs"] is not None

        # Verify DocumentLog in DB
        doc_log_id = data["id"]
        db_log = await db.documentlog.find_unique(where={"id": doc_log_id})
        assert db_log is not None
        assert db_log.status == "SUCCESS"

        # Cleanup
        await db.documentlog.delete(where={"id": doc_log_id})
        await db.template.delete(where={"id": template_id})
        await db.user.delete(where={"id": user_id})
        await db.workspace.delete(where={"id": workspace_id})


@pytest.mark.asyncio
async def test_ingest_text_unmatched():
    """
    When Gemini returns UNMATCHED in Stage 1, the DocumentLog should be
    status=UNMATCHED and no extraction should occur.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, _, workspace_id, user_id, template_id = (
            await _signup_and_create_template(client)
        )
        headers = {"Authorization": f"Bearer {token}"}

        with patch(
            "app.services.gemini_service.generate_text",
            new=AsyncMock(return_value="UNMATCHED"),
        ):
            data = await _ingest_and_wait(
                client, headers, {"rawInput": "This is an unrecognisable document."}
            )

        assert data["status"] == "UNMATCHED"
        assert data["templateId"] is None
        assert data["extractedJson"] is None

        # Cleanup
        await db.documentlog.delete(where={"id": data["id"]})
        await db.template.delete(where={"id": template_id})
        await db.user.delete(where={"id": user_id})
        await db.workspace.delete(where={"id": workspace_id})


@pytest.mark.asyncio
async def test_ingest_text_validation_failure():
    """
    When Gemini extraction returns malformed JSON, the pipeline should
    set status=FAILED and populate validationErrors.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, _, workspace_id, user_id, template_id = (
            await _signup_and_create_template(client)
        )
        headers = {"Authorization": f"Bearer {token}"}

        with patch(
            "app.services.gemini_service.generate_text",
            new=AsyncMock(side_effect=[template_id, "this is not valid json {{{"]),
        ):
            data = await _ingest_and_wait(client, headers, {"rawInput": "Invoice from Acme Corp"})

        assert data["status"] == "FAILED"
        assert data["validationErrors"] is not None

        # Cleanup
        await db.documentlog.delete(where={"id": data["id"]})
        await db.template.delete(where={"id": template_id})
        await db.user.delete(where={"id": user_id})
        await db.workspace.delete(where={"id": workspace_id})


@pytest.mark.asyncio
async def test_ingest_no_input_rejected():
    """Submitting with no rawInput and no file should return HTTP 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"empty_{uuid4().hex[:6]}@example.com"
        res = await client.post(
            "/api/v1/auth/signup",
            json={"email": email, "password": "Password123!"},
        )
        token = res.json()["access_token"]
        workspace_id = res.json()["workspace"]["id"]
        user_id = res.json()["user"]["id"]

        bad_res = await client.post(
            "/api/v1/ingest/",
            data={},  # no rawInput, no file
            headers={"Authorization": f"Bearer {token}"},
        )
        assert bad_res.status_code == 422

        # Cleanup
        await db.user.delete(where={"id": user_id})
        await db.workspace.delete(where={"id": workspace_id})


@pytest.mark.asyncio
async def test_ingest_blocked_without_key_or_fallback():
    """
    BYOAK gate: a workspace with no custom Gemini key AND platform fallback
    disabled (the default for every new workspace) must be blocked before
    any Gemini call is made — we never spend platform budget without
    explicit opt-in.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"nokey_{uuid4().hex[:8]}@example.com"
        res = await client.post(
            "/api/v1/auth/signup",
            json={"email": email, "password": "Password123!"},
        )
        assert res.status_code == 201, res.text
        data = res.json()
        token = data["access_token"]
        workspace_id = data["workspace"]["id"]
        user_id = data["user"]["id"]
        assert data["workspace"]["allowPlatformFallback"] is False

        data = await _ingest_and_wait(
            client,
            {"Authorization": f"Bearer {token}"},
            {"rawInput": "Invoice from Acme Corp, total $100."},
        )

        assert data["status"] == "FAILED"
        assert "No AI key configured" in data["validationErrors"]["error"]
        assert data["validationErrors"]["code"] == "NO_AI_KEY"

        # Cleanup
        await db.documentlog.delete(where={"id": data["id"]})
        await db.user.delete(where={"id": user_id})
        await db.workspace.delete(where={"id": workspace_id})


@pytest.mark.asyncio
async def test_ingest_file_wrong_mime_rejected():
    """Uploading a file with an unsupported MIME type should return HTTP 415."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"mime_{uuid4().hex[:6]}@example.com"
        res = await client.post(
            "/api/v1/auth/signup",
            json={"email": email, "password": "Password123!"},
        )
        token = res.json()["access_token"]
        workspace_id = res.json()["workspace"]["id"]
        user_id = res.json()["user"]["id"]

        bad_res = await client.post(
            "/api/v1/ingest/",
            files={"file": ("test.txt", b"some text content", "text/plain")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert bad_res.status_code == 415

        # Cleanup
        await db.user.delete(where={"id": user_id})
        await db.workspace.delete(where={"id": workspace_id})
