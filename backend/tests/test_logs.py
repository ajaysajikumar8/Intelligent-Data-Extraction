"""
test_logs.py — Tests for the document extraction audit log API.
"""

import pytest
from uuid import uuid4
from httpx import ASGITransport, AsyncClient

from app.core.db import db
from app.main import app

async def _signup(client: AsyncClient) -> tuple[str, str, str]:
    email = f"logs_{uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "workspaceName": "Logs WS"},
    )
    assert res.status_code == 201
    data = res.json()
    return data["access_token"], data["workspace"]["id"], data["user"]["id"]

@pytest.mark.asyncio
async def test_get_document_log():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token, workspace_id, user_id = await _signup(client)

        # 1. Create a dummy DocumentLog manually in DB
        doc_log = await db.documentlog.create(
            data={
                "workspaceId": workspace_id,
                "userId": user_id,
                "source": "API",
                "status": "SUCCESS",
                "rawInput": "This is test text",
                "extractedJson": '{"key": "value"}',  # json
            }
        )
        assert doc_log is not None

        # 2. Add a dummy WebhookDelivery
        wh = await db.webhookendpoint.create(
            data={
                "workspaceId": workspace_id,
                "url": "https://example.com/hook",
                "secret": "secret",
            }
        )
        await db.webhookdelivery.create(
            data={
                "webhookId": wh.id,
                "documentLogId": doc_log.id,
                "statusCode": 200,
                "durationMs": 150,
            }
        )

        # 3. Fetch the log via API
        res = await client.get(
            f"/api/v1/logs/{doc_log.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()

        assert data["id"] == doc_log.id
        assert data["source"] == "API"
        assert data["status"] == "SUCCESS"
        assert data["rawInput"] == "This is test text"
        assert data["extractedJson"] == {"key": "value"}
        assert len(data["webhookDeliveries"]) == 1
        assert data["webhookDeliveries"][0]["statusCode"] == 200

@pytest.mark.asyncio
async def test_get_document_log_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token, _, _ = await _signup(client)
        fake_id = str(uuid4())

        res = await client.get(
            f"/api/v1/logs/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404

@pytest.mark.asyncio
async def test_get_document_log_wrong_workspace():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token1, ws_id1, user_id1 = await _signup(client)
        token2, _, _ = await _signup(client)

        doc_log = await db.documentlog.create(
            data={
                "workspaceId": ws_id1,
                "userId": user_id1,
                "source": "MANUAL",
            }
        )
        assert doc_log is not None

        # User 2 tries to read User 1's log
        res = await client.get(
            f"/api/v1/logs/{doc_log.id}",
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert res.status_code == 404
