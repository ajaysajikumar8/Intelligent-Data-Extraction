import pytest
from uuid import uuid4
from httpx import ASGITransport, AsyncClient

from app.core.db import db
from app.main import app


@pytest.mark.asyncio
async def test_workspace_endpoints_and_dual_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"ws_owner_{uuid4().hex[:8]}@example.com"
        password = "Password123!"

        # 1. Signup to create owner user and workspace
        signup_res = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": email,
                "password": password,
                "name": "Workspace Owner",
                "workspaceName": "Acme Corp",
            },
        )
        assert signup_res.status_code == 201
        data = signup_res.json()
        token = data["access_token"]
        initial_api_key = data["workspace"]["apiKey"]
        workspace_id = data["workspace"]["id"]
        user_id = data["user"]["id"]

        # 2. Get current workspace via Bearer JWT
        res_jwt = await client.get(
            "/api/v1/workspaces/current",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_jwt.status_code == 200
        assert res_jwt.json()["name"] == "Acme Corp"
        assert res_jwt.json()["plan"]["slug"] == "free"

        # 3. Get current workspace via X-API-Key header
        res_key = await client.get(
            "/api/v1/workspaces/current",
            headers={"X-API-Key": initial_api_key},
        )
        assert res_key.status_code == 200
        assert res_key.json()["id"] == workspace_id

        # 4. Update workspace name (OWNER)
        update_res = await client.put(
            "/api/v1/workspaces/current",
            json={"name": "Acme Global Corp"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert update_res.status_code == 200
        assert update_res.json()["name"] == "Acme Global Corp"

        # 5. Rotate API Key (OWNER)
        rotate_res = await client.post(
            "/api/v1/workspaces/current/api-key/rotate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rotate_res.status_code == 200
        new_api_key = rotate_res.json()["apiKey"]
        assert new_api_key != initial_api_key

        # 6. Verify old API key fails and new API key works
        old_key_res = await client.get(
            "/api/v1/workspaces/current",
            headers={"X-API-Key": initial_api_key},
        )
        assert old_key_res.status_code == 401

        new_key_res = await client.get(
            "/api/v1/workspaces/current",
            headers={"X-API-Key": new_api_key},
        )
        assert new_key_res.status_code == 200

        # 7. Get Workspace Members
        members_res = await client.get(
            "/api/v1/workspaces/current/members",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert members_res.status_code == 200
        members = members_res.json()
        assert len(members) == 1
        assert members[0]["email"] == email

        # Cleanup
        await db.user.delete(where={"id": user_id})
        await db.workspace.delete(where={"id": workspace_id})
