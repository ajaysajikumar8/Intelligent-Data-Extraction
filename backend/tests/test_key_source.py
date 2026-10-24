"""
test_key_source.py — DocumentLog records whose Gemini key and which model ran the extraction (ADR-013).
"""

import json

import httpx
import pytest
from google.genai import errors as genai_errors
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.core.config import get_settings
from app.core.db import db
from app.core.encryption import encrypt
from app.main import app
from app.services import extraction_queue
from tests.test_ingest import _ingest_and_wait, _signup_and_create_template

PAYLOAD = json.dumps({"vendor_name": "Acme", "invoice_number": "INV-1", "total_amount": 10})


def _quota_error() -> genai_errors.ClientError:
    body = {"error": {"code": 429, "message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}}
    return genai_errors.ClientError(429, httpx.Response(429, json=body))


def _gemini(template_id: str, *, fail_for_key: str | None = None):
    """Fake generate_text: classify returns the template, extract returns PAYLOAD; one key can be out of quota."""
    async def fake(prompt: str, api_key: str | None = None, **_: object) -> str:
        if fail_for_key is not None and api_key == fail_for_key:
            raise _quota_error()
        return template_id if "document classification engine" in prompt else PAYLOAD
    return fake


async def _run_one(client: AsyncClient, token: str, fake) -> dict:
    with patch("app.services.gemini_service.generate_text", new=AsyncMock(side_effect=fake)):
        return await _ingest_and_wait(client, {"Authorization": f"Bearer {token}"}, {"rawInput": "invoice text"})


@pytest.mark.asyncio
async def test_platform_fallback_run_is_recorded_as_platform_with_the_model_used():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token, _, _, _, template_id = await _signup_and_create_template(client)  # fallback enabled
        data = await _run_one(client, token, _gemini(template_id))
        assert data["status"] == "SUCCESS"
        assert data["apiKeySource"] == "PLATFORM"
        assert data["modelUsed"] == get_settings().GEMINI_MODEL


@pytest.mark.asyncio
async def test_trial_credit_run_is_recorded_as_trial_credit():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token, _, workspace_id, _, template_id = await _signup_and_create_template(client)
        await db.workspace.update(
            where={"id": workspace_id},
            data={"allowPlatformFallback": False, "trialExtractionsRemaining": 1},
        )
        data = await _run_one(client, token, _gemini(template_id))
        assert data["status"] == "SUCCESS"
        assert data["apiKeySource"] == "TRIAL_CREDIT"


@pytest.mark.asyncio
async def test_own_key_run_is_recorded_as_workspace():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token, _, workspace_id, _, template_id = await _signup_and_create_template(client)
        await db.workspace.update(
            where={"id": workspace_id},
            data={"allowPlatformFallback": False, "geminiApiKey": encrypt("own-test-key")},
        )
        data = await _run_one(client, token, _gemini(template_id))
        assert data["status"] == "SUCCESS"
        assert data["apiKeySource"] == "WORKSPACE"


@pytest.mark.asyncio
async def test_own_key_quota_fallback_is_recorded_as_workspace_then_platform():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token, _, workspace_id, _, template_id = await _signup_and_create_template(client)  # fallback enabled
        await db.workspace.update(where={"id": workspace_id}, data={"geminiApiKey": encrypt("own-test-key")})
        data = await _run_one(client, token, _gemini(template_id, fail_for_key="own-test-key"))
        assert data["status"] == "SUCCESS"
        assert data["apiKeySource"] == "WORKSPACE_THEN_PLATFORM"


@pytest.mark.asyncio
async def test_run_that_never_reached_the_ai_records_nothing():
    """No key and no credits: the job fails before any AI call, so there is no key source or model to record."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token, _, workspace_id, _, _ = await _signup_and_create_template(client)
        await db.workspace.update(
            where={"id": workspace_id},
            data={"allowPlatformFallback": False, "trialExtractionsRemaining": 0},
        )
        res = await client.post(
            "/api/v1/ingest/", data={"rawInput": "invoice text"}, headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 202
        await extraction_queue.wait_idle()
        final = (await client.get(f"/api/v1/logs/{res.json()['id']}", headers={"Authorization": f"Bearer {token}"})).json()
        assert final["status"] == "FAILED"
        assert final["apiKeySource"] is None and final["modelUsed"] is None
