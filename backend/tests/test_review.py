"""
test_review.py — Approving / correcting documents in NEEDS_REVIEW (POST /logs/{id}/correct).
"""

import pytest
from httpx import ASGITransport, AsyncClient
from prisma.fields import Json

from app.core.db import db
from app.main import app
from tests.test_ingest import _signup_and_create_template

EXTRACTED = {"vendor_name": "Acme Corp", "invoice_number": "INV-1", "total_amount": 100.0}


async def _seed_needs_review(workspace_id: str, template_id: str, status: str = "NEEDS_REVIEW"):
    return await db.documentlog.create(
        data={
            "workspace": {"connect": {"id": workspace_id}},
            "template": {"connect": {"id": template_id}},
            "source": "MANUAL",
            "status": status,  # type: ignore[typeddict-item]
            "rawInput": "Invoice from Acme",
            "extractedJson": Json(EXTRACTED),
            "confidenceScores": Json({"vendor_name": "High", "invoice_number": "Low", "total_amount": "Medium"}),
        }
    )


@pytest.mark.asyncio
async def test_correction_updates_values_and_records_a_learning_example():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token, _, workspace_id, _, template_id = await _signup_and_create_template(client)
        headers = {"Authorization": f"Bearer {token}"}
        doc = await _seed_needs_review(workspace_id, template_id)

        res = await client.post(
            f"/api/v1/logs/{doc.id}/correct",
            json={"correctedJson": {**EXTRACTED, "invoice_number": "INV-2024-001", "total_amount": 120.5}},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "SUCCESS"
        assert res.json()["extractedJson"]["invoice_number"] == "INV-2024-001"
        assert res.json()["extractedJson"]["total_amount"] == 120.5
        assert await db.extractioncorrection.find_unique(where={"documentLogId": doc.id}) is not None


@pytest.mark.asyncio
async def test_approving_unchanged_values_does_not_record_a_correction():
    """'Approve as is' confirms the document but must not add a no-op example to future prompts."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token, _, workspace_id, _, template_id = await _signup_and_create_template(client)
        headers = {"Authorization": f"Bearer {token}"}
        doc = await _seed_needs_review(workspace_id, template_id)

        res = await client.post(f"/api/v1/logs/{doc.id}/correct", json={"correctedJson": EXTRACTED}, headers=headers)
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "SUCCESS"
        assert res.json()["extractedJson"] == EXTRACTED
        assert await db.extractioncorrection.find_unique(where={"documentLogId": doc.id}) is None


@pytest.mark.asyncio
async def test_invalid_correction_returns_field_errors_and_changes_nothing():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token, _, workspace_id, _, template_id = await _signup_and_create_template(client)
        headers = {"Authorization": f"Bearer {token}"}
        doc = await _seed_needs_review(workspace_id, template_id)

        res = await client.post(
            f"/api/v1/logs/{doc.id}/correct",
            json={"correctedJson": {**EXTRACTED, "total_amount": "not a number"}},
            headers=headers,
        )
        assert res.status_code == 422
        errors = res.json()["detail"]["errors"]
        assert [e["field"] for e in errors] == ["total_amount"]
        assert (await db.documentlog.find_unique(where={"id": doc.id})).status == "NEEDS_REVIEW"


@pytest.mark.asyncio
async def test_correction_only_once_and_only_for_needs_review_in_own_workspace():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token, _, workspace_id, _, template_id = await _signup_and_create_template(client)
        other_token, *_ = await _signup_and_create_template(client)
        headers = {"Authorization": f"Bearer {token}"}
        doc = await _seed_needs_review(workspace_id, template_id)
        finished = await _seed_needs_review(workspace_id, template_id, status="SUCCESS")
        body = {"correctedJson": EXTRACTED}

        # Another workspace cannot see it.
        res = await client.post(f"/api/v1/logs/{doc.id}/correct", json=body, headers={"Authorization": f"Bearer {other_token}"})
        assert res.status_code == 404

        # Already-finished documents are not reviewable.
        assert (await client.post(f"/api/v1/logs/{finished.id}/correct", json=body, headers=headers)).status_code == 409

        # The first approval wins; a repeat (double-click, second reviewer) is rejected.
        assert (await client.post(f"/api/v1/logs/{doc.id}/correct", json=body, headers=headers)).status_code == 200
        assert (await client.post(f"/api/v1/logs/{doc.id}/correct", json=body, headers=headers)).status_code == 409
