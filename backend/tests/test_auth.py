import pytest
from uuid import uuid4
from httpx import ASGITransport, AsyncClient

from app.core.db import db
from app.main import app


@pytest.mark.asyncio
async def test_signup_and_login_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_email = f"user_{uuid4().hex[:8]}@example.com"
        password = "SecurePassword123!"

        # 1. Signup
        signup_res = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": unique_email,
                "password": password,
                "name": "Test User",
                "workspaceName": "Test Workspace",
            },
        )
        assert signup_res.status_code == 201, signup_res.text
        data = signup_res.json()
        assert "access_token" in data
        assert data["user"]["email"] == unique_email
        assert data["user"]["role"] == "OWNER"
        assert data["workspace"]["name"] == "Test Workspace"
        token = data["access_token"]
        workspace_id = data["workspace"]["id"]
        user_id = data["user"]["id"]

        # 2. Duplicate Signup Protection
        dup_res = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": unique_email,
                "password": password,
            },
        )
        assert dup_res.status_code == 400

        # 3. Login Success
        login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": unique_email,
                "password": password,
            },
        )
        assert login_res.status_code == 200
        login_data = login_res.json()
        assert login_data["user"]["email"] == unique_email

        # 4. Login Invalid Credentials
        bad_login = await client.post(
            "/api/v1/auth/login",
            json={
                "email": unique_email,
                "password": "WrongPassword!",
            },
        )
        assert bad_login.status_code == 401

        # 5. Get Profile (/me)
        me_res = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["user"]["id"] == user_id

        # 6. Get Profile Unauthorized
        no_auth = await client.get("/api/v1/auth/me")
        assert no_auth.status_code == 401

        # Clean up database records
        await db.user.delete(where={"id": user_id})
        await db.workspace.delete(where={"id": workspace_id})
