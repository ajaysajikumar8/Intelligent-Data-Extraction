"""
test_email_verification.py — email verification, trial grant, and signup abuse limits
(docs/adr/009-email-verification-and-signup-limits.md).
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.db import db
from app.core.security import create_access_token, create_verification_token
from app.core.signup_guard import client_ip
from app.main import app


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _email(domain: str = "example.com") -> str:
    return f"verify_{uuid4().hex[:8]}@{domain}"


async def _signup(client: AsyncClient, email: str | None = None):
    return await client.post(
        "/api/v1/auth/signup",
        json={"email": email or _email(), "password": "Password123!", "name": "Verify Tester"},
    )


async def _cleanup(*signups: dict) -> None:
    for data in signups:
        await db.user.delete(where={"id": data["user"]["id"]})
        await db.workspace.delete(where={"id": data["workspace"]["id"]})


async def _verify(client: AsyncClient, data: dict):
    token = create_verification_token(data["user"]["id"], data["user"]["email"])
    return await client.post("/api/v1/auth/verify-email", json={"token": token})


async def _credits(data: dict) -> int:
    ws = await db.workspace.find_unique(where={"id": data["workspace"]["id"]})
    assert ws is not None
    return ws.trialExtractionsRemaining


# ── Verification + grant ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signup_is_unverified_and_sends_a_verification_link():
    async with _client() as client:
        with patch("app.services.email_verification.send_verification_email", new=AsyncMock(return_value=True)) as sent, \
                patch.object(get_settings(), "TRIAL_EXTRACTIONS", 5):
            res = await _signup(client)
            assert res.status_code == 201, res.text
            data = res.json()
            try:
                assert data["user"]["emailVerifiedAt"] is None
                assert data["workspace"]["trialExtractionsRemaining"] == 0
                sent.assert_awaited_once()
                to, name, link = sent.await_args.args
                assert to == data["user"]["email"] and "/verify-email?token=" in link
            finally:
                await _cleanup(data)


@pytest.mark.asyncio
async def test_verify_grants_trial_once_and_is_idempotent():
    async with _client() as client:
        with patch.object(get_settings(), "TRIAL_EXTRACTIONS", 5):
            data = (await _signup(client)).json()
            try:
                first = await _verify(client, data)
                assert first.status_code == 200, first.text
                assert first.json() == {"status": "verified", "trialExtractionsGranted": 5}
                assert await _credits(data) == 5

                again = await _verify(client, data)  # re-clicking the link
                assert again.status_code == 200
                assert again.json()["trialExtractionsGranted"] == 0
                assert await _credits(data) == 5

                me = await client.get(
                    "/api/v1/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"}
                )
                assert me.json()["user"]["emailVerifiedAt"] is not None
            finally:
                await _cleanup(data)


@pytest.mark.asyncio
async def test_verify_with_trial_disabled_verifies_without_credits():
    async with _client() as client:
        data = (await _signup(client)).json()  # conftest: TRIAL_EXTRACTIONS=0
        try:
            res = await _verify(client, data)
            assert res.status_code == 200
            assert res.json()["trialExtractionsGranted"] == 0
            assert await _credits(data) == 0
        finally:
            await _cleanup(data)


@pytest.mark.asyncio
async def test_daily_cap_verifies_but_withholds_credits():
    async with _client() as client:
        with patch.object(get_settings(), "TRIAL_EXTRACTIONS", 5), \
                patch.object(get_settings(), "TRIAL_DAILY_GRANT_CAP", 0):
            data = (await _signup(client)).json()
            try:
                res = await _verify(client, data)
                assert res.status_code == 200
                assert res.json()["trialExtractionsGranted"] == 0
                assert await _credits(data) == 0
                user = await db.user.find_unique(where={"id": data["user"]["id"]})
                assert user is not None and user.emailVerifiedAt is not None
            finally:
                await _cleanup(data)


@pytest.mark.asyncio
async def test_invalid_expired_and_wrong_purpose_tokens_are_rejected():
    async with _client() as client:
        data = (await _signup(client)).json()
        try:
            uid, email = data["user"]["id"], data["user"]["email"]
            expired = create_access_token(
                {"sub": uid, "email": email, "purpose": "verify_email"}, expires_delta=timedelta(seconds=-5)
            )
            session_token = data["access_token"]  # a login token must not verify an email
            wrong_email = create_verification_token(uid, "someone-else@example.com")
            for bad in ("not-a-token-at-all", expired, session_token, wrong_email):
                res = await client.post("/api/v1/auth/verify-email", json={"token": bad})
                assert res.status_code == 400, bad
            user = await db.user.find_unique(where={"id": uid})
            assert user is not None and user.emailVerifiedAt is None
        finally:
            await _cleanup(data)


@pytest.mark.asyncio
async def test_verification_token_is_not_a_session():
    async with _client() as client:
        data = (await _signup(client)).json()
        try:
            token = create_verification_token(data["user"]["id"], data["user"]["email"])
            res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert res.status_code == 401
        finally:
            await _cleanup(data)


# ── Resend ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resend_sends_then_rate_limits_and_skips_when_verified():
    async with _client() as client:
        with patch("app.services.email_verification.send_verification_email", new=AsyncMock(return_value=True)) as sent, \
                patch.object(get_settings(), "VERIFICATION_RESEND_LIMIT_PER_HOUR", 2):
            data = (await _signup(client)).json()
            auth = {"Authorization": f"Bearer {data['access_token']}"}
            try:
                assert sent.await_count == 1  # signup email
                for _ in range(2):
                    res = await client.post("/api/v1/auth/resend-verification", headers=auth)
                    assert res.status_code == 200 and res.json()["status"] == "sent"
                assert sent.await_count == 3

                limited = await client.post("/api/v1/auth/resend-verification", headers=auth)
                assert limited.status_code == 429
                assert int(limited.headers["Retry-After"]) > 0

                await _verify(client, data)
                done = await client.post("/api/v1/auth/resend-verification", headers=auth)
                assert done.json()["status"] == "already_verified"
            finally:
                await _cleanup(data)


# ── Signup abuse limits ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disposable_domains_are_blocked():
    async with _client() as client:
        for domain in ("mailinator.com", "foo.yopmail.com"):
            res = await _signup(client, _email(domain))
            assert res.status_code == 400
            assert "Disposable" in res.json()["detail"]


@pytest.mark.asyncio
async def test_signup_is_rate_limited_per_ip():
    async with _client() as client:
        created = []
        with patch.object(get_settings(), "SIGNUP_LIMIT_PER_IP_PER_HOUR", 2):
            try:
                for _ in range(2):
                    res = await _signup(client)
                    assert res.status_code == 201, res.text
                    created.append(res.json())
                blocked = await _signup(client)
                assert blocked.status_code == 429
                assert "Retry-After" in blocked.headers
            finally:
                await _cleanup(*created)


@pytest.mark.asyncio
async def test_signup_is_rate_limited_per_domain_but_not_for_common_providers():
    async with _client() as client:
        created = []
        with patch.object(get_settings(), "SIGNUP_LIMIT_PER_DOMAIN_PER_HOUR", 1):
            try:
                custom = f"corp-{uuid4().hex[:6]}.com"
                first = await _signup(client, _email(custom))
                assert first.status_code == 201, first.text
                created.append(first.json())
                assert (await _signup(client, _email(custom))).status_code == 429

                for _ in range(2):  # gmail.com is exempt from the domain cap
                    res = await _signup(client, _email("gmail.com"))
                    assert res.status_code == 201, res.text
                    created.append(res.json())
            finally:
                await _cleanup(*created)


def _request(host: str, xff: str | None) -> SimpleNamespace:
    headers = {"x-forwarded-for": xff} if xff else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_client_ip_trusts_forwarded_for_only_for_configured_hops():
    spoofed = "6.6.6.6, 203.0.113.9"  # left entry is client-forged; right is added by our proxy
    with patch.object(get_settings(), "TRUSTED_PROXY_HOPS", 0):
        assert client_ip(_request("10.0.0.1", spoofed)) == "10.0.0.1"
    with patch.object(get_settings(), "TRUSTED_PROXY_HOPS", 1):
        assert client_ip(_request("10.0.0.1", spoofed)) == "203.0.113.9"
        assert client_ip(_request("10.0.0.1", None)) == "10.0.0.1"
    with patch.object(get_settings(), "TRUSTED_PROXY_HOPS", 2):
        assert client_ip(_request("10.0.0.1", spoofed)) == "6.6.6.6"


# ── Plain-language validation errors (#6, #7) ──────────────────────────────


@pytest.mark.asyncio
async def test_validation_errors_are_plain_language_and_keep_field_location():
    async with _client() as client:
        res = await client.post(
            "/api/v1/auth/signup", json={"email": "user@example.test", "password": "Password123!"}
        )
        assert res.status_code == 422
        err = res.json()["detail"][0]
        assert err["loc"][-1] == "email"
        assert err["msg"] == "This email domain can't receive mail. Please use a real email address."

        res = await client.post("/api/v1/auth/signup", json={"email": "nope", "password": "short"})
        msgs = {e["loc"][-1]: e["msg"] for e in res.json()["detail"]}
        assert msgs["email"] == "Please enter a valid email address."
        assert msgs["password"] == "Password must be at least 8 characters."
