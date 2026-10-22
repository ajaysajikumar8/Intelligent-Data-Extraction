"""
test_url_safety.py — SSRF protection for outbound webhook requests.

An attacker who can set a webhook URL must not be able to make the server call
internal services (cloud metadata, localhost, private networks) or read their
responses through the ping endpoint / delivery history.
"""

import socket
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.db import db
from app.core.url_safety import (
    BLOCKED_MESSAGE,
    UnsafeUrlError,
    assert_url_allowed,
    resolve_target,
    safe_post,
)
from app.main import app
from app.services import webhook_dispatcher


# ---------------------------------------------------------------------------
# Pure URL validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/hook",
        "http://127.0.0.1/hook",
        "http://127.1/hook",                           # shorthand loopback
        "http://0.0.0.0/hook",
        "http://[::1]/hook",
        "http://169.254.169.254/latest/meta-data/",    # cloud metadata
        "http://[fd00:ec2::254]/latest/meta-data/",    # AWS IPv6 metadata
        "http://10.0.0.5/hook",
        "http://172.16.0.1/hook",
        "http://192.168.1.10/hook",
        "http://100.64.0.1/hook",                      # CGNAT
        "http://224.0.0.1/hook",                       # multicast
        "http://2130706433/hook",                      # 127.0.0.1 as a decimal number
        "http://0x7f.0.0.1/hook",                      # hex octet form
        "http://017700000001/hook",                    # octal form
        "http://[::ffff:127.0.0.1]/hook",              # IPv4-mapped IPv6
        "http://[::ffff:169.254.169.254]/hook",
        "http://[64:ff9b::a9fe:a9fe]/hook",            # metadata address wrapped in NAT64
        "http://[64:ff9b::7f00:1]/hook",               # loopback wrapped in NAT64
        "http://[64:ff9b::a00:1]/hook",                # 10.0.0.1 wrapped in NAT64
        "http://[2002:7f00:1::]/hook",                 # loopback wrapped in 6to4
    ],
)
@pytest.mark.asyncio
async def test_internal_destinations_are_blocked(url):
    with pytest.raises(UnsafeUrlError) as exc:
        await resolve_target(url)
    assert str(exc.value) == BLOCKED_MESSAGE


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/hook",
        "file:///etc/passwd",
        "gopher://example.com/",
        "http://user:secret@example.com/hook",
        "http:///nohost",
        "not a url",
    ],
)
@pytest.mark.asyncio
async def test_bad_schemes_credentials_and_garbage_are_rejected(url):
    with pytest.raises(UnsafeUrlError):
        await resolve_target(url)


@pytest.mark.asyncio
async def test_public_address_is_allowed_and_pinned():
    target = await resolve_target("https://8.8.8.8:8443/path?x=1")
    assert target.url.host == "8.8.8.8"
    assert target.url.port == 8443
    assert target.host_header == "8.8.8.8:8443"
    assert target.sni_hostname == "8.8.8.8"


@pytest.mark.asyncio
async def test_hostname_resolving_to_a_private_address_is_blocked():
    with patch("app.core.url_safety._resolve", new=AsyncMock(return_value=["10.1.2.3"])):
        with pytest.raises(UnsafeUrlError):
            await resolve_target("https://totally-public-looking.example.com/hook")


@pytest.mark.asyncio
async def test_dns64_synthesised_addresses_for_public_hosts_are_allowed():
    """
    Regression: on IPv6/NAT64 networks, DNS64 adds a 64:ff9b:: address for every IPv4-only host.
    Python flags that prefix as "reserved", which used to block ordinary public sites
    (e.g. hooks.zapier.com) outright.
    """
    answers = ["64:ff9b::12a1:e520", "18.161.229.32"]  # synthesised + real, for a public host
    with patch("app.core.url_safety._resolve", new=AsyncMock(return_value=answers)):
        target = await resolve_target("https://hooks.example.com/in")
    assert target.url.host == "64:ff9b::12a1:e520"
    assert target.sni_hostname == "hooks.example.com"


@pytest.mark.asyncio
async def test_one_bad_record_among_good_ones_blocks_the_host():
    """A host that also resolves to an internal address must be refused outright."""
    with patch("app.core.url_safety._resolve", new=AsyncMock(return_value=["93.184.216.34", "127.0.0.1"])):
        with pytest.raises(UnsafeUrlError):
            await resolve_target("https://mixed.example.com/hook")


@pytest.mark.asyncio
async def test_unresolvable_host_is_accepted_at_save_time():
    with patch("app.core.url_safety.asyncio.get_running_loop") as loop:
        loop.return_value.getaddrinfo = AsyncMock(side_effect=socket.gaierror("nope"))
        await assert_url_allowed("https://not-configured-yet.example.com/hook")  # no exception


@pytest.mark.asyncio
async def test_private_hosts_can_be_allowed_for_local_development():
    with patch.object(get_settings(), "WEBHOOK_ALLOW_PRIVATE_HOSTS", True):
        target = await resolve_target("http://127.0.0.1:9911/hook")
    assert target.url.host == "127.0.0.1"


# ---------------------------------------------------------------------------
# The request really goes to the validated IP (no DNS rebinding window)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safe_post_connects_to_the_validated_ip_and_keeps_identity():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), host=request.headers["host"], sni=request.extensions.get("sni_hostname"))
        return httpx.Response(200)

    with patch("app.core.url_safety._resolve", new=AsyncMock(return_value=["93.184.216.34"])):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            res = await safe_post(client, "https://hooks.example.com/in", content=b"{}", headers={"X-A": "1"})

    assert res.status_code == 200
    assert seen["url"] == "https://93.184.216.34/in"   # connected to the IP we validated
    assert seen["host"] == "hooks.example.com"          # Host header preserved
    assert seen["sni"] == "hooks.example.com"           # TLS name preserved


@pytest.mark.asyncio
async def test_unreachable_first_address_falls_back_to_the_next_validated_one():
    tried: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tried.append(request.url.host)
        if request.url.host == "2001:4860:4860::8888":  # e.g. IPv6 with no route on this host
            raise httpx.ConnectError("no route to host")
        return httpx.Response(200)

    with patch("app.core.url_safety._resolve", new=AsyncMock(return_value=["2001:4860:4860::8888", "8.8.8.8"])):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            res = await safe_post(client, "https://hooks.example.com/in", content=b"{}", headers={})

    assert res.status_code == 200
    assert tried == ["2001:4860:4860::8888", "8.8.8.8"]


@pytest.mark.asyncio
async def test_a_failure_after_connecting_is_not_retried_on_another_address():
    """A timeout mid-request may mean the webhook was delivered: retrying could duplicate it."""
    tried: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tried.append(request.url.host)
        raise httpx.ReadTimeout("slow endpoint")

    with patch("app.core.url_safety._resolve", new=AsyncMock(return_value=["93.184.216.34", "8.8.8.8"])):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(httpx.ReadTimeout):
                await safe_post(client, "https://hooks.example.com/in", content=b"{}", headers={})

    assert tried == ["93.184.216.34"]


@pytest.mark.asyncio
async def test_attempts_are_bounded_and_the_last_connection_error_is_raised():
    tried: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tried.append(request.url.host)
        raise httpx.ConnectError("unreachable")

    addresses = ["8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9"]
    with patch("app.core.url_safety._resolve", new=AsyncMock(return_value=addresses)):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(httpx.ConnectError):
                await safe_post(client, "https://hooks.example.com/in", content=b"{}", headers={})

    assert tried == addresses[:3]  # never more than _MAX_ADDRESS_ATTEMPTS


@pytest.mark.asyncio
async def test_an_internal_address_is_never_attempted_even_as_a_later_fallback():
    tried: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tried.append(request.url.host)
        raise httpx.ConnectError("unreachable")

    with patch("app.core.url_safety._resolve", new=AsyncMock(return_value=["8.8.8.8", "169.254.169.254"])):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(UnsafeUrlError):
                await safe_post(client, "https://hooks.example.com/in", content=b"{}", headers={})

    assert tried == []  # the whole host is refused before any connection is made


@pytest.mark.asyncio
async def test_redirects_are_never_followed():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})

    with patch("app.core.url_safety._resolve", new=AsyncMock(return_value=["93.184.216.34"])):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            res = await safe_post(client, "https://hooks.example.com/in", content=b"{}", headers={})

    assert res.status_code == 302
    assert len(calls) == 1  # the Location header was not followed


# ---------------------------------------------------------------------------
# API + delivery behaviour
# ---------------------------------------------------------------------------

async def _signup(client: AsyncClient) -> dict:
    res = await client.post(
        "/api/v1/auth/signup",
        json={"email": f"ssrf_{uuid4().hex[:8]}@example.com", "password": "Password123!"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return {
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "workspace_id": data["workspace"]["id"],
        "user_id": data["user"]["id"],
    }


async def _cleanup(ws: dict) -> None:
    await db.webhookdelivery.delete_many(where={"documentLog": {"is": {"workspaceId": ws["workspace_id"]}}})
    await db.documentlog.delete_many(where={"workspaceId": ws["workspace_id"]})
    await db.webhookendpoint.delete_many(where={"workspaceId": ws["workspace_id"]})
    await db.user.delete(where={"id": ws["user_id"]})
    await db.workspace.delete(where={"id": ws["workspace_id"]})


@pytest.mark.asyncio
async def test_api_rejects_internal_webhook_urls_on_create_and_update():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _signup(client)

        res = await client.post("/api/v1/webhooks/", json={"url": "http://169.254.169.254/latest/meta-data/"}, headers=ws["headers"])
        assert res.status_code == 422
        assert res.json()["detail"] == BLOCKED_MESSAGE

        ok = await client.post("/api/v1/webhooks/", json={"url": "https://8.8.8.8/hook"}, headers=ws["headers"])
        assert ok.status_code == 201, ok.text

        upd = await client.put(f"/api/v1/webhooks/{ok.json()['id']}", json={"url": "http://localhost:5432/"}, headers=ws["headers"])
        assert upd.status_code == 422

        await _cleanup(ws)


@pytest.mark.asyncio
async def test_ping_never_contacts_or_echoes_a_blocked_target():
    """Pre-existing (or tampered) rows must be refused at use time, and nothing may be echoed back."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _signup(client)
        created = await client.post("/api/v1/webhooks/", json={"url": "https://8.8.8.8/hook"}, headers=ws["headers"])
        wh_id = created.json()["id"]
        await db.webhookendpoint.update(where={"id": wh_id}, data={"url": "http://169.254.169.254/latest/meta-data/"})

        # Replace the *server's* outbound client (not this test's own client) and prove it is never used.
        outbound = AsyncMock()
        outbound.__aenter__.return_value = outbound
        with patch("app.api.webhooks.httpx.AsyncClient", return_value=outbound):
            res = await client.post(f"/api/v1/webhooks/{wh_id}/ping", headers=ws["headers"])

        outbound.post.assert_not_awaited()
        body = res.json()
        assert body["success"] is False
        assert body["statusCode"] is None
        assert body["responseBody"] == BLOCKED_MESSAGE
        await _cleanup(ws)


@pytest.mark.asyncio
async def test_delivery_to_a_blocked_target_is_recorded_not_sent():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ws = await _signup(client)
        created = await client.post("/api/v1/webhooks/", json={"url": "https://8.8.8.8/hook"}, headers=ws["headers"])
        wh_id = created.json()["id"]
        await db.webhookendpoint.update(where={"id": wh_id}, data={"url": "http://10.0.0.9/internal"})
        doc = await db.documentlog.create(data={
            "workspace": {"connect": {"id": ws["workspace_id"]}}, "source": "MANUAL", "status": "SUCCESS",
        })

        with patch("httpx.AsyncClient.post", new=AsyncMock()) as post:
            await webhook_dispatcher._dispatch_all(doc)

        post.assert_not_awaited()
        deliveries = await db.webhookdelivery.find_many(where={"webhookId": wh_id})
        assert len(deliveries) == 1
        assert deliveries[0].statusCode is None
        assert deliveries[0].error.startswith("Blocked:")
        assert deliveries[0].responseBody is None
        await _cleanup(ws)
