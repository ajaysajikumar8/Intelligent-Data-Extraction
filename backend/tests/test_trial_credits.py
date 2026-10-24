"""
test_trial_credits.py — Free-trial credits (docs/adr/008-free-trial-credits.md).

  • email verification (not signup) grants TRIAL_EXTRACTIONS — see test_email_verification.py
  • key routing: own key / platform fallback never spend a credit; the trial does
  • spending is atomic under concurrency; failed jobs refund, finished ones don't
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.db import db
from app.core.encryption import encrypt
from app.core.security import create_verification_token
from app.main import app
from app.services import ai_access, extraction_queue


async def _signup(client: AsyncClient) -> dict:
    res = await client.post(
        "/api/v1/auth/signup",
        json={"email": f"trial_{uuid4().hex[:8]}@example.com", "password": "Password123!"},
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _cleanup(data: dict) -> None:
    await db.user.delete(where={"id": data["user"]["id"]})
    await db.workspace.delete(where={"id": data["workspace"]["id"]})


async def _workspace(ws_id: str, **fields):
    await db.workspace.update(where={"id": ws_id}, data=fields)  # type: ignore[arg-type]
    return await db.workspace.find_unique(where={"id": ws_id})


async def _credits(ws_id: str) -> int:
    ws = await db.workspace.find_unique(where={"id": ws_id})
    assert ws is not None
    return ws.trialExtractionsRemaining


@pytest.mark.asyncio
async def test_signup_grants_nothing_until_email_verified():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch.object(get_settings(), "TRIAL_EXTRACTIONS", 5):
            data = await _signup(client)
            try:
                assert data["workspace"]["trialExtractionsRemaining"] == 0
                token = create_verification_token(data["user"]["id"], data["user"]["email"])
                res = await client.post("/api/v1/auth/verify-email", json={"token": token})
                assert res.status_code == 200, res.text
                assert await _credits(data["workspace"]["id"]) == 5
            finally:
                await _cleanup(data)


@pytest.mark.asyncio
async def test_signup_grants_nothing_when_trial_disabled():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        data = await _signup(client)  # conftest sets TRIAL_EXTRACTIONS=0
        try:
            assert data["workspace"]["trialExtractionsRemaining"] == 0
        finally:
            await _cleanup(data)


@pytest.mark.asyncio
async def test_acquire_routing_and_spending():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        data = await _signup(client)
        ws_id = data["workspace"]["id"]
        try:
            # Own key: used as-is, credits untouched.
            ws = await _workspace(ws_id, geminiApiKey=encrypt("own-key-1234567890"), trialExtractionsRemaining=2)
            access = await ai_access.acquire(ws)
            assert access.custom_api_key == "own-key-1234567890"
            assert not access.trial_credit_held and not access.allow_platform_fallback
            assert await _credits(ws_id) == 2

            # Platform fallback: credits untouched.
            ws = await _workspace(ws_id, geminiApiKey=None, allowPlatformFallback=True)
            access = await ai_access.acquire(ws)
            assert access.allow_platform_fallback and not access.trial_credit_held
            assert await _credits(ws_id) == 2

            # Trial: spends one credit and allows the platform key for this job only.
            ws = await _workspace(ws_id, allowPlatformFallback=False)
            access = await ai_access.acquire(ws)
            assert access.custom_api_key is None
            assert access.allow_platform_fallback and access.trial_credit_held
            assert await _credits(ws_id) == 1

            # Exhausted: blocked, balance never goes negative.
            await ai_access.acquire(ws)
            access = await ai_access.acquire(ws)
            assert not access.allow_platform_fallback and not access.trial_credit_held
            assert await _credits(ws_id) == 0
        finally:
            await _cleanup(data)


@pytest.mark.asyncio
async def test_concurrent_acquire_never_overspends():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        data = await _signup(client)
        ws_id = data["workspace"]["id"]
        try:
            ws = await _workspace(ws_id, trialExtractionsRemaining=3)
            results = await asyncio.gather(*(ai_access.acquire(ws) for _ in range(12)))
            assert sum(r.trial_credit_held for r in results) == 3
            assert await _credits(ws_id) == 0
        finally:
            await _cleanup(data)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome, expected_credits", [("SUCCESS", 0), ("UNMATCHED", 0), ("FAILED", 1)])
async def test_queue_refunds_only_failed_trial_jobs(outcome: str, expected_credits: int):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        data = await _signup(client)
        ws_id = data["workspace"]["id"]
        try:
            ws = await _workspace(ws_id, trialExtractionsRemaining=1)
            run = AsyncMock(return_value=SimpleNamespace(status=outcome))
            with patch("app.services.extraction_pipeline.run", new=run):
                extraction_queue.enqueue(
                    doc_log_id="doc", workspace=ws, raw_text="x",
                    file_bytes=None, mime_type=None, template_id=None,
                )
                await extraction_queue.wait_idle()

            kwargs = run.await_args.kwargs
            assert kwargs["custom_api_key"] is None and kwargs["allow_platform_fallback"] is True
            assert await _credits(ws_id) == expected_credits
        finally:
            await _cleanup(data)


@pytest.mark.asyncio
async def test_queue_refunds_when_job_times_out():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        data = await _signup(client)
        ws_id = data["workspace"]["id"]
        try:
            ws = await _workspace(ws_id, trialExtractionsRemaining=1)

            async def hang(**_):
                await asyncio.sleep(30)

            with patch.object(get_settings(), "EXTRACTION_JOB_TIMEOUT_SECONDS", 0.05), \
                 patch("app.services.extraction_pipeline.run", new=hang), \
                 patch("app.services.extraction_pipeline.fail_document", new=AsyncMock()):
                extraction_queue.enqueue(
                    doc_log_id="doc", workspace=ws, raw_text="x",
                    file_bytes=None, mime_type=None, template_id=None,
                )
                await extraction_queue.wait_idle()

            assert await _credits(ws_id) == 1
        finally:
            await _cleanup(data)
