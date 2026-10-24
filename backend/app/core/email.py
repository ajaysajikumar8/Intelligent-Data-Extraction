import logging
from html import escape

import httpx

from app.core.config import get_settings

logger = logging.getLogger("app.core.email")

_RESEND_URL = "https://api.resend.com/emails"


async def send_email(to: str, subject: str, html: str) -> bool:
    """
    Send one transactional email through Resend. Never raises: a mail outage must not break the
    calling flow (the user can request a resend). Returns True if the provider accepted it.

    With RESEND_API_KEY unset (local dev / tests) nothing is sent; the message is logged so the
    verification link can be copied from the server output.
    """
    settings = get_settings()
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — email to %s not sent. Subject: %s\n%s", to, subject, html)
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                _RESEND_URL,
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={"from": settings.EMAIL_FROM, "to": [to], "subject": subject, "html": html},
            )
        if res.status_code >= 400:
            logger.error("Resend rejected email (HTTP %s): %s", res.status_code, res.text[:300])
            return False
        return True
    except httpx.HTTPError as exc:
        logger.error("Resend request failed: %s", exc)
        return False


async def send_verification_email(to: str, name: str | None, link: str) -> bool:
    greeting = f"Hi {escape(name)}," if name else "Hi,"
    html = (
        f"<p>{greeting}</p>"
        "<p>Confirm your email address to activate your workspace and unlock your free trial "
        "extractions.</p>"
        f'<p><a href="{escape(link)}">Verify my email</a></p>'
        "<p>This link expires soon. If you didn't create an account, you can ignore this email.</p>"
    )
    return await send_email(to, "Verify your email address", html)
