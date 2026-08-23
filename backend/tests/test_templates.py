"""
test_templates.py — Template CRUD lifecycle tests.

Tests workspace-scoped isolation, creation, listing, update (with version
increment), and soft-delete — all without touching Gemini.
"""

import pytest
from uuid import uuid4
from httpx import ASGITransport, AsyncClient

from app.core.db import db
from app.main import app


@pytest.mark.asyncio
async def test_template_crud_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # ── Setup: create a workspace via signup ────────────────────────────
        email = f"tmpl_{uuid4().hex[:8]}@example.com"
        signup_res = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": email,
                "password": "Password123!",
                "name": "Template Tester",
                "workspaceName": "Template Test WS",
            },
        )
        assert signup_res.status_code == 201, signup_res.text
        token = signup_res.json()["access_token"]
        workspace_id = signup_res.json()["workspace"]["id"]
        user_id = signup_res.json()["user"]["id"]
        headers = {"Authorization": f"Bearer {token}"}

        # ── 1. Create template ──────────────────────────────────────────────
        create_res = await client.post(
            "/api/v1/templates",
            json={
                "name": "Invoice Template",
                "description": "Extracts invoice fields",
                "schema": {
                    "vendor_name": "string",
                    "invoice_number": "string",
                    "total_amount": "number",
                    "currency": "string",
                },
            },
            headers=headers,
        )
        assert create_res.status_code == 201, create_res.text
        tmpl = create_res.json()
        template_id = tmpl["id"]
        assert tmpl["name"] == "Invoice Template"
        assert tmpl["version"] == 1
        assert tmpl["isActive"] is True
        assert tmpl["fieldCount"] == 4

        # ── 2. List templates — should contain the one we just created ──────
        list_res = await client.get("/api/v1/templates", headers=headers)
        assert list_res.status_code == 200
        templates = list_res.json()
        assert any(t["id"] == template_id for t in templates)

        # ── 3. Get single template ──────────────────────────────────────────
        get_res = await client.get(f"/api/v1/templates/{template_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["id"] == template_id

        # ── 4. Update template name (no schema change → version stays at 1) ─
        upd_res = await client.put(
            f"/api/v1/templates/{template_id}",
            json={"name": "Updated Invoice Template"},
            headers=headers,
        )
        assert upd_res.status_code == 200
        assert upd_res.json()["name"] == "Updated Invoice Template"
        assert upd_res.json()["version"] == 1  # No schema change

        # ── 5. Update schema → version should increment to 2 ────────────────
        schema_upd_res = await client.put(
            f"/api/v1/templates/{template_id}",
            json={
                "schema": {
                    "vendor_name": "string",
                    "invoice_number": "string",
                    "total_amount": "number",
                    "currency": "string",
                    "due_date": "string",   # new field
                }
            },
            headers=headers,
        )
        assert schema_upd_res.status_code == 200
        assert schema_upd_res.json()["version"] == 2
        assert schema_upd_res.json()["fieldCount"] == 5

        # ── 6. 404 for a non-existent template ───────────────────────────────
        not_found = await client.get(
            f"/api/v1/templates/{uuid4()}", headers=headers
        )
        assert not_found.status_code == 404

        # ── 7. Soft-delete ───────────────────────────────────────────────────
        del_res = await client.delete(
            f"/api/v1/templates/{template_id}", headers=headers
        )
        assert del_res.status_code == 204

        # After soft-delete it should NOT appear in the default active listing
        list_after = await client.get("/api/v1/templates", headers=headers)
        assert not any(t["id"] == template_id for t in list_after.json())

        # But with include_inactive=true it SHOULD appear
        list_incl = await client.get(
            "/api/v1/templates?include_inactive=true", headers=headers
        )
        assert any(t["id"] == template_id for t in list_incl.json())

        # ── Cleanup ──────────────────────────────────────────────────────────
        await db.template.delete(where={"id": template_id})
        await db.user.delete(where={"id": user_id})
        await db.workspace.delete(where={"id": workspace_id})


@pytest.mark.asyncio
async def test_template_workspace_isolation():
    """A template created in workspace A should not be visible from workspace B."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create workspace A
        res_a = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": f"ws_a_{uuid4().hex[:6]}@example.com",
                "password": "Password123!",
                "workspaceName": "Workspace A",
            },
        )
        assert res_a.status_code == 201
        token_a = res_a.json()["access_token"]
        ws_a_id = res_a.json()["workspace"]["id"]
        user_a_id = res_a.json()["user"]["id"]

        # Create workspace B
        res_b = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": f"ws_b_{uuid4().hex[:6]}@example.com",
                "password": "Password123!",
                "workspaceName": "Workspace B",
            },
        )
        assert res_b.status_code == 201
        token_b = res_b.json()["access_token"]
        ws_b_id = res_b.json()["workspace"]["id"]
        user_b_id = res_b.json()["user"]["id"]

        # Create a template in workspace A
        tmpl_res = await client.post(
            "/api/v1/templates",
            json={"name": "Private Template", "schema": {"field": "string"}},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert tmpl_res.status_code == 201
        template_id = tmpl_res.json()["id"]

        # Workspace B should NOT see it in its list
        list_b = await client.get(
            "/api/v1/templates",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert not any(t["id"] == template_id for t in list_b.json())

        # Workspace B should get 404 when fetching it directly
        get_b = await client.get(
            f"/api/v1/templates/{template_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert get_b.status_code == 404

        # Cleanup
        await db.template.delete(where={"id": template_id})
        await db.user.delete(where={"id": user_a_id})
        await db.workspace.delete(where={"id": ws_a_id})
        await db.user.delete(where={"id": user_b_id})
        await db.workspace.delete(where={"id": ws_b_id})
