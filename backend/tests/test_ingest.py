"""
test_ingest.py — Ingestion pipeline tests with Gemini mocked.

We patch `app.services.gemini_service.generate_text` so tests run without
a real Gemini API key and without network calls, while still exercising the
full pipeline logic — quota checking, DocumentLog lifecycle, Stage 1 classify,
Stage 2 extract, Stage 3 validate.

All tests hit POST /api/v1/ingest/ — the single unified endpoint.
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
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


# ---------------------------------------------------------------------------
# Per-workspace in-flight cap (batch uploads)
# ---------------------------------------------------------------------------

async def _seed_logs(workspace_id: str, status: str, count: int, age_hours: int = 0) -> None:
    created_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    for _ in range(count):
        await db.documentlog.create(
            data={
                "workspace": {"connect": {"id": workspace_id}},
                "source": "MANUAL",
                "status": status,  # type: ignore[typeddict-item]
                "createdAt": created_at,
            }
        )


@pytest.mark.asyncio
async def test_ingest_rejected_when_workspace_has_too_many_in_flight():
    """A workspace at its in-flight cap gets 429 + Retry-After and no new DocumentLog row."""
    limited = get_settings().model_copy(update={"EXTRACTION_MAX_IN_FLIGHT_PER_WORKSPACE": 2})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, _, workspace_id, _, _ = await _signup_and_create_template(client)
        headers = {"Authorization": f"Bearer {token}"}

        # Two live jobs fill the cap; finished and long-dead (orphaned) rows must not count.
        await _seed_logs(workspace_id, "PENDING", 1)
        await _seed_logs(workspace_id, "PROCESSING", 1)
        await _seed_logs(workspace_id, "SUCCESS", 3)
        await _seed_logs(workspace_id, "PROCESSING", 3, age_hours=48)
        before = await db.documentlog.count(where={"workspaceId": workspace_id})

        with patch("app.api.ingest.get_settings", return_value=limited):
            res = await client.post("/api/v1/ingest/", data={"rawInput": "invoice text"}, headers=headers)

        assert res.status_code == 429, res.text
        assert res.headers["Retry-After"] == "15"
        assert await db.documentlog.count(where={"workspaceId": workspace_id}) == before


@pytest.mark.asyncio
async def test_ingest_allowed_below_in_flight_cap():
    """Finished documents free up capacity: only queued/running rows count toward the cap."""
    limited = get_settings().model_copy(update={"EXTRACTION_MAX_IN_FLIGHT_PER_WORKSPACE": 2})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, _, workspace_id, _, template_id = await _signup_and_create_template(client)
        headers = {"Authorization": f"Bearer {token}"}
        await _seed_logs(workspace_id, "PENDING", 1)
        await _seed_logs(workspace_id, "SUCCESS", 5)

        payload = json.dumps({"vendor_name": "Acme", "invoice_number": "1", "total_amount": 1})
        with patch("app.api.ingest.get_settings", return_value=limited), patch(
            "app.services.gemini_service.generate_text",
            new=AsyncMock(side_effect=[template_id, payload]),
        ):
            data = await _ingest_and_wait(client, headers, {"rawInput": "invoice text"})

        assert data["status"] == "SUCCESS"


# ---------------------------------------------------------------------------
# Mixed batch: auto-detect classifies every document independently
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_detect_routes_each_document_to_its_own_template():
    """Two documents submitted together (no template picked) each end up on the right template."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, _, workspace_id, _, invoice_tmpl_id = await _signup_and_create_template(client)
        headers = {"Authorization": f"Bearer {token}"}

        resume = await client.post(
            "/api/v1/templates",
            json={
                "name": "Resume Template",
                "description": "Extracts candidate details from resumes.",
                "schema": {"candidate_name": "string", "years_experience": "number"},
            },
            headers=headers,
        )
        assert resume.status_code == 201, resume.text
        resume_tmpl_id = resume.json()["id"]

        async def fake_gemini(prompt: str, **_: object) -> str:
            if "document classification engine" in prompt:
                return invoice_tmpl_id if "INVOICE" in prompt else resume_tmpl_id
            if "invoice_number" in prompt:
                return json.dumps({"vendor_name": "Acme", "invoice_number": "INV-1", "total_amount": 10})
            return json.dumps({"candidate_name": "Jane Doe", "years_experience": 7})

        with patch("app.services.gemini_service.generate_text", new=AsyncMock(side_effect=fake_gemini)):
            responses = await asyncio.gather(
                client.post("/api/v1/ingest/", data={"rawInput": "INVOICE from Acme, total 10"}, headers=headers),
                client.post("/api/v1/ingest/", data={"rawInput": "Jane Doe, senior engineer, 7 years"}, headers=headers),
            )
            assert [r.status_code for r in responses] == [202, 202]
            await extraction_queue.wait_idle()

        invoice_log, resume_log = [
            (await client.get(f"/api/v1/logs/{r.json()['id']}", headers=headers)).json() for r in responses
        ]
        assert invoice_log["status"] == "SUCCESS" and invoice_log["templateId"] == invoice_tmpl_id
        assert invoice_log["extractedJson"]["invoice_number"] == "INV-1"
        assert resume_log["status"] == "SUCCESS" and resume_log["templateId"] == resume_tmpl_id
        assert resume_log["extractedJson"]["candidate_name"] == "Jane Doe"


# ---------------------------------------------------------------------------
# POST /logs/{id}/retry — "Try again" for failed extractions
# ---------------------------------------------------------------------------

async def _seed_failed(workspace_id: str, code: str = "AI_BUSY", **extra: object):
    from prisma.fields import Json

    data = {
        "workspace": {"connect": {"id": workspace_id}},
        "source": "MANUAL",
        "status": "FAILED",
        "rawInput": "INVOICE from Acme, total 10",
        "validationErrors": Json({"error": "failed", "code": code}),
        "processingMs": 1234,
    }
    data.update(extra)
    return await db.documentlog.create(data=data)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_retry_requeues_failed_text_document_and_succeeds():
    """A transient failure can be retried in place: same id, back to PENDING, then SUCCESS."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, _, workspace_id, _, template_id = await _signup_and_create_template(client)
        headers = {"Authorization": f"Bearer {token}"}
        failed = await _seed_failed(workspace_id)
        before = await db.documentlog.count(where={"workspaceId": workspace_id})

        payload = json.dumps({"vendor_name": "Acme", "invoice_number": "INV-1", "total_amount": 10})
        with patch(
            "app.services.gemini_service.generate_text",
            new=AsyncMock(side_effect=[template_id, payload]),
        ):
            res = await client.post(f"/api/v1/logs/{failed.id}/retry", headers=headers)
            assert res.status_code == 202, res.text
            assert res.json()["id"] == failed.id
            assert res.json()["status"] == "PENDING"
            assert res.json()["validationErrors"] is None
            await extraction_queue.wait_idle()

        final = (await client.get(f"/api/v1/logs/{failed.id}", headers=headers)).json()
        assert final["status"] == "SUCCESS"
        assert final["extractedJson"]["invoice_number"] == "INV-1"
        # Retried in place: no duplicate row, so the monthly quota is not charged twice.
        assert await db.documentlog.count(where={"workspaceId": workspace_id}) == before


@pytest.mark.asyncio
async def test_retry_reuses_the_matched_template_and_skips_classification():
    """When the failed document already had a template, the retry goes straight to extraction."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, _, workspace_id, _, template_id = await _signup_and_create_template(client)
        headers = {"Authorization": f"Bearer {token}"}
        failed = await _seed_failed(workspace_id, "TIMEOUT", template={"connect": {"id": template_id}})

        payload = json.dumps({"vendor_name": "Acme", "invoice_number": "INV-2", "total_amount": 5})
        mock = AsyncMock(side_effect=[payload])  # a single call: extraction only
        with patch("app.services.gemini_service.generate_text", new=mock):
            res = await client.post(f"/api/v1/logs/{failed.id}/retry", headers=headers)
            assert res.status_code == 202, res.text
            await extraction_queue.wait_idle()

        assert mock.await_count == 1
        assert (await client.get(f"/api/v1/logs/{failed.id}", headers=headers)).json()["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_retry_rejected_for_files_non_retryable_and_finished_documents():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, _, workspace_id, _, _ = await _signup_and_create_template(client)
        headers = {"Authorization": f"Bearer {token}"}

        file_doc = await _seed_failed(workspace_id, fileName="invoice.pdf", mimeType="application/pdf")
        blocked = await _seed_failed(workspace_id, "CONTENT_BLOCKED")
        done = await db.documentlog.create(
            data={"workspace": {"connect": {"id": workspace_id}}, "source": "MANUAL", "status": "SUCCESS", "rawInput": "x"}
        )

        res = await client.post(f"/api/v1/logs/{file_doc.id}/retry", headers=headers)
        assert res.status_code == 409 and "not stored" in res.json()["detail"]
        for doc in (blocked, done):
            res = await client.post(f"/api/v1/logs/{doc.id}/retry", headers=headers)
            assert res.status_code == 409, res.text

        # Rejected retries must leave the documents untouched.
        assert (await db.documentlog.find_unique(where={"id": blocked.id})).status == "FAILED"


@pytest.mark.asyncio
async def test_retry_cannot_be_claimed_twice_and_is_workspace_scoped():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, _, workspace_id, _, template_id = await _signup_and_create_template(client)
        other_token, *_ = await _signup_and_create_template(client)
        headers = {"Authorization": f"Bearer {token}"}
        failed = await _seed_failed(workspace_id)

        payload = json.dumps({"vendor_name": "Acme", "invoice_number": "INV-3", "total_amount": 1})
        with patch(
            "app.services.gemini_service.generate_text",
            new=AsyncMock(side_effect=[template_id, payload]),
        ):
            # Another workspace cannot see or retry it.
            res = await client.post(
                f"/api/v1/logs/{failed.id}/retry", headers={"Authorization": f"Bearer {other_token}"}
            )
            assert res.status_code == 404

            first, second = await asyncio.gather(
                client.post(f"/api/v1/logs/{failed.id}/retry", headers=headers),
                client.post(f"/api/v1/logs/{failed.id}/retry", headers=headers),
            )
            assert sorted([first.status_code, second.status_code]) == [202, 409]
            await extraction_queue.wait_idle()
