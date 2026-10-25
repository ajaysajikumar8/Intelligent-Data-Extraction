"""
test_activity.py — The workspace activity log (ADR-015): what gets recorded, what never does, and who can read it.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from prisma.fields import Json

from app.core.config import get_settings
from app.core.db import db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.services import activity, extraction_queue, webhook_dispatcher

SECRET_GEMINI_KEY = "AIzaSy-THIS-MUST-NEVER-BE-LOGGED"
SECRET_WEBHOOK_TOKEN = "tok_9f8e7d6c5b4a_SECRET"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _signup(client: AsyncClient) -> dict:
    res = await client.post(
        "/api/v1/auth/signup",
        json={"email": f"act_{uuid4().hex[:8]}@example.com", "password": "Password123!", "workspaceName": "Activity WS"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    data["headers"] = {"Authorization": f"Bearer {data['access_token']}"}
    return data


async def _entries(client: AsyncClient, ws: dict, **params) -> list[dict]:
    res = await client.get("/api/v1/activity", params={"limit": 100, **params}, headers=ws["headers"])
    assert res.status_code == 200, res.text
    return res.json()


def _actions(entries: list[dict]) -> list[str]:
    return [e["action"] for e in entries]


@pytest.mark.asyncio
async def test_signup_and_login_are_recorded_with_ip_and_failed_logins_only_for_known_accounts(client):
    ws = await _signup(client)
    email = ws["user"]["email"]

    ok = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    bad = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
    unknown = await client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"})
    assert (ok.status_code, bad.status_code, unknown.status_code) == (200, 401, 401)

    entries = await _entries(client, ws, category="auth")
    assert set(_actions(entries)) == {"auth.signed_up", "auth.login", "auth.login_failed"}
    failed = next(e for e in entries if e["action"] == "auth.login_failed")
    assert failed["actorLabel"] == email and failed["ipAddress"]
    # A guess at an email that does not exist belongs to no workspace, so it is not recorded anywhere.
    assert await db.activitylog.count(where={"actorLabel": "nobody@example.com"}) == 0


@pytest.mark.asyncio
async def test_failed_logins_are_capped_per_hour(client):
    ws = await _signup(client)
    for _ in range(25):
        await client.post("/api/v1/auth/login", json={"email": ws["user"]["email"], "password": "wrong"})
    assert await db.activitylog.count(where={"workspaceId": ws["workspace"]["id"], "action": "auth.login_failed"}) == 20


@pytest.mark.asyncio
async def test_template_changes_are_recorded_and_noop_updates_are_not(client):
    ws = await _signup(client)
    created = await client.post(
        "/api/v1/templates", json={"name": "Invoice", "schema": {"total": "number"}}, headers=ws["headers"]
    )
    tid = created.json()["id"]
    await client.put(f"/api/v1/templates/{tid}", json={"name": "Invoice v2", "schema": {"total": "number", "date": "string"}}, headers=ws["headers"])
    await client.put(f"/api/v1/templates/{tid}", json={"isActive": False}, headers=ws["headers"])
    await client.put(f"/api/v1/templates/{tid}", json={"isActive": False}, headers=ws["headers"])  # no change
    await client.delete(f"/api/v1/templates/{tid}", headers=ws["headers"])
    lib = await client.get("/api/v1/templates/library", headers=ws["headers"])
    await client.post(f"/api/v1/templates/library/{lib.json()[0]['slug']}/duplicate", headers=ws["headers"])

    entries = await _entries(client, ws, category="templates")
    assert _actions(entries).count("template.updated") == 2  # the repeated deactivation changed nothing
    assert _actions(entries).count("template.created") == 2
    assert "template.deleted" in _actions(entries)
    summaries = " | ".join(e["summary"] for e in entries)
    assert "renamed from" in summaries and "fields changed (now version 2)" in summaries and "deactivated" in summaries
    assert all(e["actorLabel"] == ws["user"]["email"] and e["actorUserId"] == ws["user"]["id"] for e in entries)
    assert all(e["ipAddress"] is None for e in entries)  # routine config changes do not keep an IP


@pytest.mark.asyncio
async def test_changes_made_with_an_api_key_are_attributed_to_the_api_key(client):
    ws = await _signup(client)
    res = await client.post(
        "/api/v1/templates", json={"name": "Via API", "schema": {"a": "string"}}, headers={"X-API-Key": ws["workspace"]["apiKey"]}
    )
    assert res.status_code == 201
    entry = next(e for e in await _entries(client, ws, category="templates") if e["action"] == "template.created")
    assert entry["actorLabel"] == "API key" and entry["actorUserId"] is None


@pytest.mark.asyncio
async def test_webhook_events_store_the_host_only_never_the_path_or_token(client):
    ws = await _signup(client)
    url = f"https://example.com/hooks/{SECRET_WEBHOOK_TOKEN}?key={SECRET_WEBHOOK_TOKEN}"
    created = await client.post("/api/v1/webhooks/", json={"url": url, "eventTypes": ["SUCCESS"]}, headers=ws["headers"])
    assert created.status_code == 201, created.text
    wid, secret = created.json()["id"], created.json()["secret"]
    await client.put(f"/api/v1/webhooks/{wid}", json={"isActive": False}, headers=ws["headers"])
    await client.put(f"/api/v1/webhooks/{wid}", json={"url": f"https://example.org/{SECRET_WEBHOOK_TOKEN}"}, headers=ws["headers"])
    await client.delete(f"/api/v1/webhooks/{wid}", headers=ws["headers"])

    entries = await _entries(client, ws, category="webhooks")
    assert _actions(entries).count("webhook.created") == 1 and "webhook.deleted" in _actions(entries)
    blob = json.dumps(entries)
    assert SECRET_WEBHOOK_TOKEN not in blob and secret not in blob
    assert "example.com" in blob and "disabled" in blob and "example.org" in blob


@pytest.mark.asyncio
async def test_webhook_auto_disable_is_recorded_as_the_system(client):
    ws = await _signup(client)
    created = await client.post("/api/v1/webhooks/", json={"url": "https://example.com/h"}, headers=ws["headers"])
    wid = created.json()["id"]
    await db.webhookendpoint.update(where={"id": wid}, data={"failureCount": webhook_dispatcher.AUTO_DISABLE_THRESHOLD - 1})
    endpoint = await db.webhookendpoint.find_unique(where={"id": wid})
    await webhook_dispatcher._increment_failure(endpoint)

    entry = next(e for e in await _entries(client, ws, category="webhooks") if e["action"] == "webhook.auto_disabled")
    assert entry["actorLabel"] == "System" and entry["actorUserId"] is None


@pytest.mark.asyncio
async def test_key_events_are_recorded_with_ip_and_never_contain_the_secret(client):
    ws = await _signup(client)
    old_api_key = ws["workspace"]["apiKey"]
    with patch("app.services.gemini_service.validate_api_key", new=AsyncMock(return_value=True)):
        await client.put("/api/v1/workspaces/current/gemini-key", json={"apiKey": SECRET_GEMINI_KEY}, headers=ws["headers"])
        await client.put("/api/v1/workspaces/current/gemini-key", json={"apiKey": SECRET_GEMINI_KEY + "2"}, headers=ws["headers"])
    await client.delete("/api/v1/workspaces/current/gemini-key", headers=ws["headers"])
    rotated = await client.post("/api/v1/workspaces/current/api-key/rotate", headers=ws["headers"])
    inbound = await client.post("/api/v1/webhooks/inbound/rotate", headers=ws["headers"])
    await client.put("/api/v1/workspaces/current", json={"name": "Renamed WS"}, headers=ws["headers"])
    await client.put("/api/v1/workspaces/current/platform-fallback", json={"enabled": False}, headers=ws["headers"])

    keys = await _entries(client, ws, category="keys")
    assert _actions(keys).count("gemini_key.set") == 2 and "gemini_key.removed" in _actions(keys)
    assert {"api_key.rotated", "inbound_secret.rotated", "platform_fallback.disabled"} <= set(_actions(keys))
    summaries = [e["summary"] for e in keys if e["action"] == "gemini_key.set"]
    assert sorted(summaries) == ["Own Gemini API key added", "Own Gemini API key replaced"]
    for e in keys:
        if e["action"].startswith(("gemini_key.", "api_key.", "inbound_secret.")):
            assert e["ipAddress"], e["action"]
    everything = json.dumps(await _entries(client, ws))
    for secret in (SECRET_GEMINI_KEY, old_api_key, rotated.json()["apiKey"], inbound.json()["inboundSecret"]):
        assert secret not in everything
    assert "workspace.renamed" in everything


@pytest.mark.asyncio
async def test_review_and_retry_are_recorded_and_the_reviewer_is_stored_on_the_correction(client):
    ws = await _signup(client)
    wid = ws["workspace"]["id"]
    tmpl = await client.post("/api/v1/templates", json={"name": "Inv", "schema": {"total": "number"}}, headers=ws["headers"])
    tid = tmpl.json()["id"]
    docs = [
        await db.documentlog.create(
            data={
                "workspace": {"connect": {"id": wid}}, "template": {"connect": {"id": tid}}, "source": "MANUAL",
                "status": "NEEDS_REVIEW", "rawInput": "x", "extractedJson": Json({"total": 10.0}),
            }
        )
        for _ in range(2)
    ]
    await client.post(f"/api/v1/logs/{docs[0].id}/correct", json={"correctedJson": {"total": 12.5}}, headers=ws["headers"])
    await client.post(f"/api/v1/logs/{docs[1].id}/correct", json={"correctedJson": {"total": 10.0}}, headers=ws["headers"])
    failed = await db.documentlog.create(
        data={"workspace": {"connect": {"id": wid}}, "source": "MANUAL", "status": "FAILED", "rawInput": "x",
              "validationErrors": Json({"error": "busy", "code": "AI_BUSY"})}
    )
    with patch("app.services.gemini_service.generate_text", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await client.post(f"/api/v1/logs/{failed.id}/retry", headers=ws["headers"])
        await extraction_queue.wait_idle()

    entries = await _entries(client, ws, category="documents")
    assert {"document.corrected", "document.approved", "document.retried"} <= set(_actions(entries))
    correction = await db.extractioncorrection.find_unique(where={"documentLogId": docs[0].id})
    assert correction.correctedByUserId == ws["user"]["id"]
    assert await db.extractioncorrection.find_unique(where={"documentLogId": docs[1].id}) is None


@pytest.mark.asyncio
async def test_only_owners_can_read_and_workspaces_are_isolated(client):
    a, b = await _signup(client), await _signup(client)
    await client.put("/api/v1/workspaces/current", json={"name": "A renamed"}, headers=a["headers"])

    assert all(e["summary"] for e in await _entries(client, b))
    assert "workspace.renamed" not in _actions(await _entries(client, b))
    assert "workspace.renamed" in _actions(await _entries(client, a))

    member = await db.user.create(
        data={"email": f"member_{uuid4().hex[:6]}@example.com", "passwordHash": hash_password("Password123!"),
              "workspaceId": a["workspace"]["id"], "role": "MEMBER"}
    )
    token = create_access_token({"sub": member.id, "workspace_id": member.workspaceId, "role": "MEMBER"})
    assert (await client.get("/api/v1/activity", headers={"Authorization": f"Bearer {token}"})).status_code == 403
    assert (await client.get("/api/v1/activity", headers={"X-API-Key": a["workspace"]["apiKey"]})).status_code == 401
    assert (await client.get("/api/v1/activity", params={"category": "nope"}, headers=a["headers"])).status_code == 422
    assert (await client.get("/api/v1/activity")).status_code == 401


@pytest.mark.asyncio
async def test_pagination_and_newest_first(client):
    ws = await _signup(client)
    for i in range(4):
        await client.put("/api/v1/workspaces/current", json={"name": f"Name {i}"}, headers=ws["headers"])
    page1 = await _entries(client, ws, category="workspace", limit=2)
    page2 = await _entries(client, ws, category="workspace", limit=2, skip=2)
    assert [e["summary"] for e in page1][0].endswith('"Name 3"')
    assert len(page1) == 2 and len(page2) == 2
    assert {e["id"] for e in page1}.isdisjoint({e["id"] for e in page2})


@pytest.mark.asyncio
async def test_recording_failures_never_break_the_action(client):
    ws = await _signup(client)
    broken_db = MagicMock()
    broken_db.activitylog.create = AsyncMock(side_effect=RuntimeError("db down"))
    with patch("app.services.activity.db", new=broken_db):
        res = await client.put("/api/v1/workspaces/current", json={"name": "Still works"}, headers=ws["headers"])
    assert res.status_code == 200 and res.json()["name"] == "Still works"


@pytest.mark.asyncio
async def test_old_entries_are_purged_after_the_retention_period(client):
    ws = await _signup(client)
    wid = ws["workspace"]["id"]
    old = datetime.now(timezone.utc) - timedelta(days=400)
    await db.activitylog.create(data={"workspaceId": wid, "actorLabel": "x", "action": "old.thing", "summary": "old", "createdAt": old})

    with patch("app.services.activity.get_settings", return_value=get_settings().model_copy(update={"ACTIVITY_RETENTION_DAYS": 0})):
        assert await activity.purge_expired() == 0  # 0 = keep forever
    assert await db.activitylog.count(where={"action": "old.thing"}) == 1

    assert await activity.purge_expired() >= 1  # default retention is 365 days
    assert await db.activitylog.count(where={"action": "old.thing"}) == 0
    assert await db.activitylog.count(where={"workspaceId": wid, "action": "auth.signed_up"}) == 1  # recent entries stay


@pytest.mark.asyncio
async def test_summaries_are_capped_and_ip_is_dropped_for_non_security_actions(client):
    ws = await _signup(client)
    wid = ws["workspace"]["id"]
    await activity.record(wid, "template.updated", "x" * 1000, actor=activity.SYSTEM, ip="203.0.113.9")
    await activity.record(wid, "auth.login", "Signed in", actor=activity.SYSTEM, ip="203.0.113.9")
    rows = {r.action: r for r in await db.activitylog.find_many(where={"workspaceId": wid, "actorLabel": "System"})}
    assert len(rows["template.updated"].summary) == 300
    assert rows["template.updated"].ipAddress is None  # a routine change never keeps the IP, even if one is passed
    assert rows["auth.login"].ipAddress == "203.0.113.9"
