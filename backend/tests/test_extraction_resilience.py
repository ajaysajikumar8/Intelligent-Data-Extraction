"""
test_extraction_resilience.py — Failure classification, retries and the queue.

Covers docs/adr/006-async-extraction-queue.md:
  • raw provider errors are never stored/exposed (classification)
  • transient provider errors are retried; others are not
  • the in-process queue: timeout, backpressure, concurrency, shutdown, crash recovery
  • inbound adapters now route the workspace key/fallback through the same queue
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from google.genai import errors as genai_errors
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.db import db
from app.main import app
from app.services import extraction_pipeline, extraction_queue, failures, gemini_service
from app.services.failures import FailureCode

RAW_MARKERS = ("503", "UNAVAILABLE", "high demand", "secret-internal-detail")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api_error(cls: type[genai_errors.APIError], code: int, status: str = "UNAVAILABLE"):
    body = {"error": {"code": code, "message": "high demand", "status": status}}
    return cls(code, httpx.Response(code, json=body))


async def _make_workspace(client: AsyncClient, *, fallback: bool = True) -> dict:
    res = await client.post(
        "/api/v1/auth/signup",
        json={"email": f"resil_{uuid4().hex[:8]}@example.com", "password": "Password123!"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    ws_id = data["workspace"]["id"]
    if fallback:
        await db.workspace.update(where={"id": ws_id}, data={"allowPlatformFallback": True})
    return {
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "workspace_id": ws_id,
        "user_id": data["user"]["id"],
        "inbound_secret": data["workspace"]["inboundSecret"],
    }


async def _make_template(client: AsyncClient, headers: dict) -> str:
    res = await client.post(
        "/api/v1/templates",
        json={
            "name": "Invoice Template",
            "description": "Invoices.",
            "schema": {"vendor_name": "string", "total_amount": "number"},
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def _cleanup(ws: dict) -> None:
    await db.documentlog.delete_many(where={"workspaceId": ws["workspace_id"]})
    await db.template.delete_many(where={"workspaceId": ws["workspace_id"]})
    await db.user.delete(where={"id": ws["user_id"]})
    await db.workspace.delete(where={"id": ws["workspace_id"]})


async def _final_log(client: AsyncClient, ws: dict, doc_id: str) -> dict:
    await extraction_queue.wait_idle()
    res = await client.get(f"/api/v1/logs/{doc_id}", headers=ws["headers"])
    assert res.status_code == 200, res.text
    return res.json()


def _assert_no_raw_leak(validation_errors: dict) -> None:
    blob = json.dumps(validation_errors)
    for marker in RAW_MARKERS:
        assert marker not in blob, f"raw provider text leaked: {marker!r}"


# ---------------------------------------------------------------------------
# Classification (pure)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_api_error(genai_errors.ServerError, 503), FailureCode.AI_BUSY),
        (_api_error(genai_errors.ServerError, 500, "INTERNAL"), FailureCode.AI_BUSY),
        (_api_error(genai_errors.ClientError, 429, "RESOURCE_EXHAUSTED"), FailureCode.RATE_LIMITED),
        (_api_error(genai_errors.ClientError, 401, "UNAUTHENTICATED"), FailureCode.AI_KEY_INVALID),
        (_api_error(genai_errors.ClientError, 403, "PERMISSION_DENIED"), FailureCode.AI_KEY_INVALID),
        (_api_error(genai_errors.ClientError, 400, "INVALID_ARGUMENT"), FailureCode.UNPROCESSABLE),
        (gemini_service.EmptyGeminiResponse("blocked"), FailureCode.CONTENT_BLOCKED),
        (httpx.ConnectError("secret-internal-detail"), FailureCode.AI_BUSY),
        (asyncio.TimeoutError(), FailureCode.AI_BUSY),
        (ValueError("secret-internal-detail"), FailureCode.INTERNAL),
    ],
)
def test_classify_maps_to_safe_failure(exc, expected):
    result = failures.classify(exc)
    assert result.code == expected
    assert not any(marker in result.message for marker in RAW_MARKERS)
    assert result.to_json() == {"error": result.message, "code": expected.value}


def test_only_server_and_transport_errors_are_transient():
    assert failures.is_transient(_api_error(genai_errors.ServerError, 503))
    assert failures.is_transient(httpx.ReadTimeout("t"))
    assert not failures.is_transient(_api_error(genai_errors.ClientError, 429, "RESOURCE_EXHAUSTED"))
    assert not failures.is_transient(_api_error(genai_errors.ClientError, 400, "INVALID_ARGUMENT"))
    assert not failures.is_transient(ValueError("x"))


# ---------------------------------------------------------------------------
# Retry behaviour through the full pipeline
# ---------------------------------------------------------------------------

async def _submit(client, ws, text="Invoice from Acme, total $10") -> str:
    res = await client.post("/api/v1/ingest/", data={"rawInput": text}, headers=ws["headers"])
    assert res.status_code == 202, res.text
    return res.json()["id"]


@pytest.mark.asyncio
async def test_transient_error_is_retried_then_succeeds():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _make_workspace(client)
        template_id = await _make_template(client, ws["headers"])
        payload = json.dumps({"vendor_name": "Acme", "total_amount": 10})
        gen = AsyncMock(side_effect=[_api_error(genai_errors.ServerError, 503), template_id, payload])

        with patch("app.services.extraction_pipeline._RETRY_BASE_DELAY_S", 0), \
             patch("app.services.gemini_service.generate_text", new=gen):
            doc_id = await _submit(client, ws)
            log = await _final_log(client, ws, doc_id)

        assert log["status"] == "SUCCESS", log
        assert gen.await_count == 3  # 503 (retried) + classify + extract
        await _cleanup(ws)


@pytest.mark.asyncio
async def test_persistent_overload_fails_with_friendly_message():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _make_workspace(client)
        await _make_template(client, ws["headers"])
        gen = AsyncMock(side_effect=_api_error(genai_errors.ServerError, 503))

        with patch("app.services.extraction_pipeline._RETRY_BASE_DELAY_S", 0), \
             patch("app.services.gemini_service.generate_text", new=gen):
            doc_id = await _submit(client, ws)
            log = await _final_log(client, ws, doc_id)

        assert log["status"] == "FAILED"
        assert log["validationErrors"]["code"] == "AI_BUSY"
        _assert_no_raw_leak(log["validationErrors"])
        assert "pipeline_error" not in log["validationErrors"]
        assert gen.await_count == extraction_pipeline._MAX_ATTEMPTS
        await _cleanup(ws)


@pytest.mark.asyncio
async def test_unparseable_ai_output_is_a_friendly_failure():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _make_workspace(client)
        template_id = await _make_template(client, ws["headers"])
        gen = AsyncMock(side_effect=[template_id, "this is not json {{{"])

        with patch("app.services.gemini_service.generate_text", new=gen):
            doc_id = await _submit(client, ws)
            log = await _final_log(client, ws, doc_id)

        assert log["status"] == "FAILED"
        assert log["validationErrors"]["code"] == "BAD_AI_OUTPUT"
        assert "Expecting value" not in json.dumps(log["validationErrors"])
        await _cleanup(ws)


@pytest.mark.asyncio
async def test_non_transient_error_is_not_retried():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _make_workspace(client)
        await _make_template(client, ws["headers"])
        gen = AsyncMock(side_effect=_api_error(genai_errors.ClientError, 400, "INVALID_ARGUMENT"))

        with patch("app.services.extraction_pipeline._RETRY_BASE_DELAY_S", 0), \
             patch("app.services.gemini_service.generate_text", new=gen):
            doc_id = await _submit(client, ws)
            log = await _final_log(client, ws, doc_id)

        assert log["status"] == "FAILED"
        assert log["validationErrors"]["code"] == "UNPROCESSABLE"
        assert gen.await_count == 1
        await _cleanup(ws)


@pytest.mark.asyncio
async def test_progress_is_visible_during_retry_and_cleared_when_done():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _make_workspace(client)
        template_id = await _make_template(client, ws["headers"])
        payload = json.dumps({"vendor_name": "Acme", "total_amount": 10})
        seen: dict = {}
        calls = 0

        async def scripted(prompt: str, api_key=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise _api_error(genai_errors.ServerError, 503)
            if calls == 2:  # the retry: progress must already say so
                doc = await db.documentlog.find_first(where={"workspaceId": ws["workspace_id"]})
                seen.update(status=doc.status, progress=doc.progress)
                return template_id
            return payload

        with patch("app.services.extraction_pipeline._RETRY_BASE_DELAY_S", 0), \
             patch("app.services.gemini_service.generate_text", new=scripted):
            doc_id = await _submit(client, ws)
            log = await _final_log(client, ws, doc_id)

        assert seen["status"] == "PROCESSING"
        assert seen["progress"] == {
            "stage": "CLASSIFYING", "attempt": 2,
            "maxAttempts": extraction_pipeline._MAX_ATTEMPTS, "retryReason": "AI_BUSY",
        }
        assert log["status"] == "SUCCESS"
        assert log["progress"] is None  # nothing in flight any more
        await _cleanup(ws)


@pytest.mark.asyncio
async def test_hung_provider_call_is_cut_off_and_retried():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _make_workspace(client)
        template_id = await _make_template(client, ws["headers"])
        payload = json.dumps({"vendor_name": "Acme", "total_amount": 10})
        calls = 0

        async def scripted(prompt: str, api_key=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                await asyncio.sleep(30)  # hangs; must be cut off by the per-call timeout
            return template_id if calls == 2 else payload

        with patch("app.services.extraction_pipeline._CALL_TIMEOUT_S", 0.1), \
             patch("app.services.extraction_pipeline._RETRY_BASE_DELAY_S", 0), \
             patch("app.services.gemini_service.generate_text", new=scripted):
            doc_id = await _submit(client, ws)
            log = await _final_log(client, ws, doc_id)

        assert log["status"] == "SUCCESS", log
        assert calls == 3
        await _cleanup(ws)


@pytest.mark.asyncio
async def test_log_detail_endpoint_returns_progress_and_confidence():
    """Regression: GET /logs/{id} used to copy fields by hand and dropped these two."""
    from prisma.fields import Json

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _make_workspace(client)
        doc = await db.documentlog.create(data={
            "workspace": {"connect": {"id": ws["workspace_id"]}}, "source": "MANUAL", "status": "PROCESSING",
            "progress": Json({"stage": "EXTRACTING", "attempt": 2, "maxAttempts": 3, "retryReason": "AI_BUSY"}),
            "confidenceScores": Json({"total_amount": "Low"}),
        })

        res = await client.get(f"/api/v1/logs/{doc.id}", headers=ws["headers"])

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["progress"]["retryReason"] == "AI_BUSY"
        assert body["progress"]["attempt"] == 2
        assert body["confidenceScores"] == {"total_amount": "Low"}
        await _cleanup(ws)


# ---------------------------------------------------------------------------
# Queue guarantees
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_timeout_marks_document_failed():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _make_workspace(client)
        await _make_template(client, ws["headers"])

        async def hang(**_):
            await asyncio.sleep(30)

        with patch.object(get_settings(), "EXTRACTION_JOB_TIMEOUT_SECONDS", 0.2), \
             patch("app.services.extraction_pipeline.run", new=hang):
            doc_id = await _submit(client, ws)
            log = await _final_log(client, ws, doc_id)

        assert log["status"] == "FAILED"
        assert log["validationErrors"]["code"] == "TIMEOUT"
        await _cleanup(ws)


@pytest.mark.asyncio
async def test_full_queue_rejects_before_creating_a_log():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _make_workspace(client)
        before = await db.documentlog.count(where={"workspaceId": ws["workspace_id"]})

        with patch.object(get_settings(), "EXTRACTION_MAX_BACKLOG", 0):
            res = await client.post("/api/v1/ingest/", data={"rawInput": "x"}, headers=ws["headers"])

        assert res.status_code == 503
        assert res.headers["retry-after"] == "30"
        assert await db.documentlog.count(where={"workspaceId": ws["workspace_id"]}) == before
        await _cleanup(ws)


@pytest.mark.asyncio
async def test_concurrency_is_capped():
    running = 0
    peak = 0

    async def slow_run(**_):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1

    workspace = SimpleNamespace(id="ws", geminiApiKey=None, allowPlatformFallback=True)
    with patch.object(get_settings(), "EXTRACTION_MAX_CONCURRENCY", 2), \
         patch("app.services.extraction_pipeline.run", new=slow_run):
        for i in range(6):
            extraction_queue.enqueue(
                doc_log_id=f"doc-{i}", workspace=workspace,
                raw_text="x", file_bytes=None, mime_type=None, template_id=None,
            )
        await extraction_queue.wait_idle()

    assert peak == 2


@pytest.mark.asyncio
async def test_shutdown_interrupts_in_flight_jobs():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _make_workspace(client)
        await _make_template(client, ws["headers"])

        async def hang(**_):
            await asyncio.sleep(30)

        with patch("app.services.extraction_pipeline.run", new=hang):
            doc_id = await _submit(client, ws)
            await asyncio.sleep(0.05)  # let the job start
            await extraction_queue.shutdown(grace_seconds=0.05)

        log = (await client.get(f"/api/v1/logs/{doc_id}", headers=ws["headers"])).json()
        assert log["status"] == "FAILED"
        assert log["validationErrors"]["code"] == "INTERRUPTED"
        await _cleanup(ws)


@pytest.mark.asyncio
async def test_recover_orphans_only_touches_stale_rows():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _make_workspace(client)
        stale = await db.documentlog.create(data={
            "workspace": {"connect": {"id": ws["workspace_id"]}}, "source": "MANUAL",
            "status": "PROCESSING", "createdAt": datetime.now(timezone.utc) - timedelta(hours=1),
        })
        fresh = await db.documentlog.create(data={
            "workspace": {"connect": {"id": ws["workspace_id"]}}, "source": "MANUAL", "status": "PENDING",
        })

        assert await extraction_queue.recover_orphans() >= 1

        stale = await db.documentlog.find_unique(where={"id": stale.id})
        fresh = await db.documentlog.find_unique(where={"id": fresh.id})
        assert stale.status == "FAILED" and stale.validationErrors["code"] == "INTERRUPTED"
        assert fresh.status == "PENDING"
        await _cleanup(ws)


# ---------------------------------------------------------------------------
# Inbound adapters share the queue (regression: they used to drop the key/fallback)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inbound_extraction_uses_workspace_fallback_setting():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _make_workspace(client, fallback=True)
        template_id = await _make_template(client, ws["headers"])
        payload = json.dumps({"vendor_name": "Acme", "total_amount": 10})

        with patch("app.services.gemini_service.generate_text", new=AsyncMock(side_effect=[template_id, payload])):
            res = await client.post(
                f"/api/v1/inbound/{ws['inbound_secret']}", data={"rawInput": "Invoice from Acme, $10"}
            )
            assert res.status_code == 202, res.text
            doc_id = res.json()["document_log_id"]
            await extraction_queue.wait_idle()

        log = await db.documentlog.find_unique(where={"id": doc_id})
        assert log.status == "SUCCESS", log.validationErrors
        await _cleanup(ws)
