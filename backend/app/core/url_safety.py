"""
url_safety.py — SSRF protection for outbound requests to customer-supplied URLs.

Why
---
Webhook URLs are typed in by customers and the server then makes requests to
them (deliveries and the "ping" test, which even returns the response body). A
URL such as ``http://169.254.169.254/latest/meta-data/`` (cloud credentials) or
``http://localhost:5432`` would make *our* server fetch internal resources on the
attacker's behalf (Server-Side Request Forgery).

What this module does
---------------------
  • Only http/https, no ``user:pass@`` credentials.
  • The hostname is *resolved here* and every resulting address must be public:
    private, loopback, link-local (incl. cloud metadata), CGNAT, multicast,
    reserved and unspecified ranges are refused. Resolving first also defeats
    numeric tricks (``http://2130706433/``, ``http://0x7f.0.0.1/``) and
    IPv4-mapped IPv6 (``::ffff:127.0.0.1``).
  • `safe_post` sends the request to the *validated IP* (with the original
    ``Host`` header and TLS server name), so DNS cannot change its answer between
    the check and the connection (DNS rebinding). Redirects are never followed.

Local development can opt out with WEBHOOK_ALLOW_PRIVATE_HOSTS=true.

Residual risk: this is application-level defence. Production should also restrict
egress at the network layer (security group / egress proxy) — defence in depth.
"""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

_MAX_ADDRESS_ATTEMPTS = 3  # bound the worst-case delivery time when several addresses are unreachable

BLOCKED_MESSAGE = (
    "Webhook URL must point to a public server. Internal, private and loopback "
    "addresses are not allowed."
)


class UnsafeUrlError(ValueError):
    """The URL must not be requested. The message is safe to show to the user."""


class UnresolvableHostError(UnsafeUrlError):
    """The hostname does not resolve (yet). Allowed at save time, fails at delivery."""


@dataclass(frozen=True)
class PinnedTarget:
    """Where to actually send the request: the validated IP, keeping the original identity."""

    url: httpx.URL
    host_header: str
    sni_hostname: str | None  # TLS server name for https; None for http


_NAT64 = ipaddress.ip_network("64:ff9b::/96")  # RFC 6052 well-known prefix used by DNS64/NAT64


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """
    The IPv4 address an IPv6 address merely *carries*, if any:
      • ::ffff:a.b.c.d   IPv4-mapped
      • 64:ff9b::a.b.c.d NAT64 — added by DNS64 for IPv4-only hosts on IPv6/NAT64 networks
      • 2002:aabb:ccdd:: 6to4
    Such an address is as safe or unsafe as the IPv4 inside it.
    """
    if ip.ipv4_mapped:
        return ip.ipv4_mapped
    if ip in _NAT64:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if ip.sixtofour:
        return ip.sixtofour
    return None


def _forbidden(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])  # drop IPv6 scope id
    if isinstance(ip, ipaddress.IPv6Address):
        ip = _embedded_ipv4(ip) or ip  # judge the real destination, not its wrapper
    return (
        not ip.is_global
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _parse(url: str) -> httpx.URL:
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL:
        raise UnsafeUrlError("Webhook URL is not valid.") from None
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError("Webhook URL must use http or https.")
    if not parsed.host:
        raise UnsafeUrlError("Webhook URL is not valid.")
    if parsed.userinfo:
        raise UnsafeUrlError("Webhook URL must not contain a username or password.")
    return parsed


async def _resolve(host: str, port: int) -> list[str]:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise UnresolvableHostError("Webhook URL host could not be resolved.") from None
    return list(dict.fromkeys(info[4][0] for info in infos))


async def resolve_targets(url: str, *, allow_private: bool | None = None) -> list[PinnedTarget]:
    """
    Validate `url` and return every validated destination, in resolver order, one per address.

    All addresses are checked before any is returned, so a caller can try them in turn
    (like a browser would) without ever touching an unvalidated one.
    Raises UnsafeUrlError (or UnresolvableHostError) when the URL must not be requested.
    """
    if allow_private is None:
        allow_private = get_settings().WEBHOOK_ALLOW_PRIVATE_HOSTS

    parsed = _parse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = await _resolve(parsed.host, port)
    if not addresses:
        raise UnresolvableHostError("Webhook URL host could not be resolved.")

    # Every record must be public: a host that also resolves to an internal
    # address could otherwise be picked by the OS resolver later.
    if not allow_private and any(_forbidden(a) for a in addresses):
        raise UnsafeUrlError(BLOCKED_MESSAGE)

    default_port = 443 if parsed.scheme == "https" else 80
    host_header = parsed.host if parsed.port in (None, default_port) else f"{parsed.host}:{parsed.port}"
    return [
        PinnedTarget(
            url=parsed.copy_with(host=address.split("%")[0]),
            host_header=host_header,
            sni_hostname=parsed.host if parsed.scheme == "https" else None,
        )
        for address in addresses
    ]


async def resolve_target(url: str, *, allow_private: bool | None = None) -> PinnedTarget:
    """Validate `url` and return the first (preferred) validated destination."""
    return (await resolve_targets(url, allow_private=allow_private))[0]


async def assert_url_allowed(url: str) -> None:
    """
    Save-time check (create/update webhook). A hostname that does not resolve yet
    is accepted — customers may configure DNS afterwards — because delivery
    re-validates every time and refuses anything internal.
    """
    try:
        await resolve_target(url)
    except UnresolvableHostError:
        return


async def safe_post(
    client: httpx.AsyncClient,
    url: str,
    *,
    content: bytes,
    headers: dict[str, str],
) -> httpx.Response:
    """
    POST to a customer URL, only ever connecting to a validated public address.

    Like a browser, each validated address is tried in turn if the previous one cannot be
    connected to (e.g. the first is IPv6 but this host has no IPv6 route). Only
    *connection* failures fall through to the next address: after a timeout or error
    mid-request the webhook may already have been delivered, so retrying could duplicate it.
    """
    last_error: httpx.TransportError | None = None
    for target in (await resolve_targets(url))[:_MAX_ADDRESS_ATTEMPTS]:
        extensions = {"sni_hostname": target.sni_hostname} if target.sni_hostname else {}
        try:
            return await client.post(
                target.url,
                content=content,
                headers={**headers, "Host": target.host_header},
                extensions=extensions,
                follow_redirects=False,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            last_error = exc
    assert last_error is not None  # resolve_targets never returns an empty list
    raise last_error
