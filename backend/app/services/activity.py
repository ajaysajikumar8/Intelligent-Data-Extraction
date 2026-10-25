"""
activity.py — Append-only record of who changed what in a workspace (ADR-015).

`record()` is called from the endpoints that change security-relevant or configuration state. It is
deliberately fail-safe: a problem writing the log is logged and swallowed, so recording an event can
never fail the action it describes.

Rules for callers
-----------------
  * `summary` is a short human sentence. It must NEVER contain a secret (API keys, webhook secrets,
    passwords, tokens), a document's contents, or a full webhook URL (those often embed tokens in the
    path or query: use `describe_url`).
  * `action` is a dotted string. Add new ones to `ACTION_CATEGORIES` so the Activity page can filter them.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from prisma.models import User

from app.core.config import get_settings
from app.core.db import db

logger = logging.getLogger("app.services.activity")

_MAX_SUMMARY = 300

# Only these actions keep the caller's IP address (security events). Routine configuration changes do not.
_IP_PREFIXES = ("auth.", "api_key.", "gemini_key.", "inbound_secret.")

# Activity page filter: category -> action prefixes.
ACTION_CATEGORIES: dict[str, tuple[str, ...]] = {
    "auth": ("auth.",),
    "keys": ("api_key.", "gemini_key.", "inbound_secret.", "platform_fallback."),
    "webhooks": ("webhook.",),
    "templates": ("template.",),
    "documents": ("document.",),
    "workspace": ("workspace.",),
}


@dataclass(frozen=True)
class Actor:
    """Who did it. `label` is a snapshot, so the entry stays readable if the user is later removed."""

    user_id: str | None
    label: str


SYSTEM = Actor(None, "System")
API_KEY = Actor(None, "API key")


def actor_for(user: User | None) -> Actor:
    """The signed-in user, or the API key for requests authenticated with X-API-Key only."""
    return Actor(user.id, user.email) if user else API_KEY


def describe_url(url: str) -> str:
    """Host only: paths and query strings of webhook URLs frequently carry secrets."""
    host = urlsplit(url).hostname or "unknown host"
    return host


async def record(
    workspace_id: str,
    action: str,
    summary: str,
    *,
    actor: Actor,
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    max_per_hour: int | None = None,
) -> None:
    """
    Append one entry. Never raises.

    `max_per_hour` caps how many entries of this action a workspace can write per hour, so an attacker
    hammering a login form cannot flood the table.
    """
    try:
        if max_per_hour is not None:
            since = datetime.now(timezone.utc) - timedelta(hours=1)
            recent = await db.activitylog.count(
                where={"workspaceId": workspace_id, "action": action, "createdAt": {"gte": since}}
            )
            if recent >= max_per_hour:
                return

        await db.activitylog.create(
            data={
                "workspaceId": workspace_id,
                "actorUserId": actor.user_id,
                "actorLabel": actor.label[:200],
                "action": action,
                "targetType": target_type,
                "targetId": target_id,
                "summary": summary[:_MAX_SUMMARY],
                "ipAddress": ip if ip and action.startswith(_IP_PREFIXES) else None,
            }
        )
    except Exception as exc:  # noqa: BLE001 — recording must never break the action being recorded
        logger.error("Could not record activity %s for workspace %s: %s", action, workspace_id, exc)


async def purge_expired() -> int:
    """Delete entries older than ACTIVITY_RETENTION_DAYS (0 = keep forever). Returns the number deleted."""
    days = get_settings().ACTIVITY_RETENTION_DAYS
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = await db.activitylog.delete_many(where={"createdAt": {"lt": cutoff}})
    if deleted:
        logger.info("Purged %d activity log entries older than %d days", deleted, days)
    return deleted
