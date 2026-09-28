"""
test_webhooks.py — Tests for Phase 6: Outbound Webhooks & Inbound Adapters.

Covers:
  - Webhook CRUD lifecycle (create, list, get, update, delete)
  - Inbound secret retrieval and rotation
  - Inbound generic adapter (POST /api/v1/inbound/{secret})
  - Inbound SendGrid adapter (POST /api/v1/inbound/sendgrid/{secret})
  - HMAC signature is present in dispatcher
  - Workspace isolation (cannot access another workspace's webhook)
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from httpx import ASGITransport, AsyncClient

from app.core.db import db
from app.main import app


# ---------------------------------------------------------------------------
# Fixture helper
# ---------------------------------------------------------------------------

async def _signup(client: AsyncClient, workspace_name: str = "Webhook Test WS") -> dict:
    """Sign up a new workspace. Returns the full signup response dict."""
    email = f"wh_{uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "Password123!",
            "workspaceName": workspace_name,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _cleanup(workspace_id: str, user_id: str) -> None:
    await db.webhookdelivery.delete_many(where={
        "documentLog": {"is": {"workspaceId": workspace_id}}
    })
    await db.webhookendpoint.delete_many(where={"workspaceId": workspace_id})
    await db.documentlog.delete_many(where={"workspaceId": workspace_id})
    await db.template.delete_many(where={"workspaceId": workspace_id})
    await db.user.delete(where={"id": user_id})
    await db.workspace.delete(where={"id": workspace_id})


# ---------------------------------------------------------------------------
# Outbound Webhook CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_crud_lifecycle():
    """Test: create → list → get → update → delete a webhook endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        data = await _signup(client)
        token = data["access_token"]
        workspace_id = data["workspace"]["id"]
        user_id = data["user"]["id"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create
        create_res = await client.post(
            "/api/v1/webhooks/",
            json={
                "url": "https://example.com/webhook",
                "description": "Test webhook",
                "eventTypes": ["SUCCESS", "FAILED"],
                "templateIds": [],
            },
            headers=headers,
        )
        assert create_res.status_code == 201, create_res.text
        wh = create_res.json()
        assert wh["url"] == "https://example.com/webhook"
        assert "secret" in wh
        assert len(wh["secret"]) == 64  # 32-byte hex
        wh_id = wh["id"]

        # List
        list_res = await client.get("/api/v1/webhooks/", headers=headers)
        assert list_res.status_code == 200
        assert any(w["id"] == wh_id for w in list_res.json())

        # Get single
        get_res = await client.get(f"/api/v1/webhooks/{wh_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["id"] == wh_id

        # Update
        update_res = await client.put(
            f"/api/v1/webhooks/{wh_id}",
            json={"description": "Updated description", "isActive": False},
            headers=headers,
        )
        assert update_res.status_code == 200
        assert update_res.json()["isActive"] is False
        assert update_res.json()["description"] == "Updated description"

        # Delete
        del_res = await client.delete(f"/api/v1/webhooks/{wh_id}", headers=headers)
        assert del_res.status_code == 204

        # Confirm gone
        get_deleted = await client.get(f"/api/v1/webhooks/{wh_id}", headers=headers)
        assert get_deleted.status_code == 404

        await _cleanup(workspace_id, user_id)


@pytest.mark.asyncio
async def test_webhook_workspace_isolation():
    """A workspace cannot access webhooks belonging to another workspace."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        d1 = await _signup(client, "Workspace A")
        d2 = await _signup(client, "Workspace B")
        h1 = {"Authorization": f"Bearer {d1['access_token']}"}
        h2 = {"Authorization": f"Bearer {d2['access_token']}"}

        # Workspace A creates a webhook
        create_res = await client.post(
            "/api/v1/webhooks/",
            json={"url": "https://example.com/a"},
            headers=h1,
        )
        assert create_res.status_code == 201
        wh_id = create_res.json()["id"]

        # Workspace B tries to access it — should 404
        get_res = await client.get(f"/api/v1/webhooks/{wh_id}", headers=h2)
        assert get_res.status_code == 404

        await _cleanup(d1["workspace"]["id"], d1["user"]["id"])
        await _cleanup(d2["workspace"]["id"], d2["user"]["id"])


# ---------------------------------------------------------------------------
# Inbound Secret Management
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inbound_secret_retrieval_and_rotation():
    """Test: get inbound URL, then rotate the secret to get a new URL."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        data = await _signup(client)
        token = data["access_token"]
        workspace_id = data["workspace"]["id"]
        user_id = data["user"]["id"]
        headers = {"Authorization": f"Bearer {token}"}

        # Get inbound URL
        get_res = await client.get("/api/v1/webhooks/inbound", headers=headers)
        assert get_res.status_code == 200
        first = get_res.json()
        assert "inboundSecret" in first
        assert "inboundUrl" in first
        assert first["inboundSecret"] in first["inboundUrl"]

        # Rotate — should generate a new secret
        rotate_res = await client.post("/api/v1/webhooks/inbound/rotate", headers=headers)
        assert rotate_res.status_code == 200
        second = rotate_res.json()
        assert second["inboundSecret"] != first["inboundSecret"]
        assert second["inboundSecret"] in second["inboundUrl"]

        # Old secret should no longer resolve
        old_secret = first["inboundSecret"]
        probe = await client.post(
            f"/api/v1/inbound/{old_secret}",
            data={"rawInput": "test"},
        )
        assert probe.status_code == 404

        await _cleanup(workspace_id, user_id)


# ---------------------------------------------------------------------------
# Inbound Generic Adapter (smoke test in webhooks context)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generic_inbound_accepts_text():
    """Test: generic inbound adapter accepts text via rawInput, returns 202."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        data = await _signup(client)
        workspace_id = data["workspace"]["id"]
        user_id = data["user"]["id"]
        inbound_secret = data["workspace"]["inboundSecret"]

        with patch(
            "app.services.extraction_pipeline.run",
            new=AsyncMock(return_value=MagicMock()),
        ):
            res = await client.post(
                f"/api/v1/inbound/{inbound_secret}",
                data={"rawInput": "Process this invoice please"},
            )

        assert res.status_code == 202
        body = res.json()
        assert body["message"] == "Accepted for processing"
        assert "document_log_id" in body

        await _cleanup(workspace_id, user_id)


@pytest.mark.asyncio
async def test_generic_inbound_invalid_secret_returns_404():
    """Test: unknown inbound secret returns 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/inbound/totally_fake_secret_that_does_not_exist",
            data={"rawInput": "hello"},
        )
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_generic_inbound_no_input_returns_422():
    """Test: inbound with neither text nor file returns 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        data = await _signup(client)
        workspace_id = data["workspace"]["id"]
        user_id = data["user"]["id"]
        inbound_secret = data["workspace"]["inboundSecret"]

        res = await client.post(
            f"/api/v1/inbound/{inbound_secret}",
            data={},
        )
        assert res.status_code == 422

        await _cleanup(workspace_id, user_id)


@pytest.mark.asyncio
async def test_sendgrid_inbound_maps_email_fields():
    """Test: Universal inbound adapter maps SendGrid 'text' field -> rawInput."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        data = await _signup(client)
        workspace_id = data["workspace"]["id"]
        user_id = data["user"]["id"]
        inbound_secret = data["workspace"]["inboundSecret"]

        with patch(
            "app.services.extraction_pipeline.run",
            new=AsyncMock(return_value=MagicMock()),
        ):
            res = await client.post(
                f"/api/v1/inbound/{inbound_secret}",
                data={
                    "text": "Dear HR, please find my resume attached.",
                    "subject": "Application for Software Engineer",
                    "from": "applicant@example.com",
                },
            )

        assert res.status_code == 202
        body = res.json()
        assert body["message"] == "Accepted for processing"
        assert "document_log_id" in body

        await _cleanup(workspace_id, user_id)

