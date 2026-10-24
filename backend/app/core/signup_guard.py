"""
Signup abuse guards (docs/adr/009-email-verification-and-signup-limits.md): client-IP
resolution, in-process sliding-window rate limiting, and a disposable-email blocklist.
"""

import logging
import time
from collections import deque

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

logger = logging.getLogger("app.core.signup_guard")

_WINDOW_SECONDS = 3600
_SWEEP_THRESHOLD = 5000

# Mainstream providers host millions of real users, so a per-domain cap would lock out honest
# signups. They are exempt from the domain limit (the per-IP limit and verification still apply).
COMMON_PROVIDER_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "ymail.com", "icloud.com", "me.com", "proton.me", "protonmail.com",
    "aol.com", "gmx.com", "zoho.com", "fastmail.com",
})

# Well-known throwaway providers. A static list is a first filter, not a guarantee: new
# domains appear daily. Email verification and the daily grant cap remain the real controls.
DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org", "sharklasers.com",
    "grr.la", "10minutemail.com", "10minutemail.net", "tempmail.com", "temp-mail.org", "temp-mail.io",
    "tempmailo.com", "tempail.com", "throwawaymail.com", "yopmail.com", "yopmail.net", "yopmail.fr",
    "trashmail.com", "trashmail.net", "getnada.com", "nada.email", "maildrop.cc", "dispostable.com",
    "fakeinbox.com", "mailnesia.com", "mintemail.com", "mohmal.com", "emailondeck.com", "moakt.com",
    "burnermail.io", "spamgourmet.com", "mytemp.email", "tmpmail.org", "tmpmail.net", "discard.email",
    "mailcatch.com", "inboxkitten.com", "harakirimail.com", "mail.tm", "1secmail.com", "1secmail.net",
    "33mail.com", "spambox.us", "tempinbox.com", "emailfake.com", "fakemail.net", "minuteinbox.com",
})


class SlidingWindowLimiter:
    """Per-key sliding window counter. In-process: with N instances the effective limit is N×."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str, limit: int, window: float = _WINDOW_SECONDS) -> int:
        """Record an attempt. Returns 0 if allowed, else seconds until the oldest hit expires."""
        now = time.monotonic()
        if len(self._hits) > _SWEEP_THRESHOLD:
            self._sweep(now, window)
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= window:
            hits.popleft()
        if len(hits) >= limit:
            return max(1, int(window - (now - hits[0])))
        hits.append(now)
        return 0

    def _sweep(self, now: float, window: float) -> None:
        for key in [k for k, h in self._hits.items() if not h or now - h[-1] >= window]:
            del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    """Resolve the caller's IP, trusting X-Forwarded-For only for the configured proxy hops."""
    hops = get_settings().TRUSTED_PROXY_HOPS
    if hops > 0:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"


def enforce_limit(scope: str, key: str, limit: int) -> None:
    """Raise 429 (with Retry-After) when `key` exceeded `limit` attempts in the last hour."""
    retry_after = limiter.hit(f"{scope}:{key}", limit)
    if retry_after:
        logger.warning("RATE_LIMITED scope=%s key=%s limit=%s/h", scope, key, limit)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower()


def is_disposable(email: str) -> bool:
    domain = email_domain(email)
    # Also match subdomains of a listed provider (e.g. x.mailinator.com).
    return any(domain == d or domain.endswith("." + d) for d in DISPOSABLE_DOMAINS)


def enforce_signup_limits(request: Request, email: str) -> None:
    """Disposable-domain block, then per-IP and per-domain rate limits. Raises HTTPException."""
    settings = get_settings()
    if is_disposable(email):
        logger.warning("SIGNUP_BLOCKED disposable domain=%s", email_domain(email))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Disposable email addresses aren't supported. Please use a permanent email address.",
        )
    enforce_limit("signup-ip", client_ip(request), settings.SIGNUP_LIMIT_PER_IP_PER_HOUR)
    domain = email_domain(email)
    if domain not in COMMON_PROVIDER_DOMAINS:
        enforce_limit("signup-domain", domain, settings.SIGNUP_LIMIT_PER_DOMAIN_PER_HOUR)
