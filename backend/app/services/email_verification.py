"""
Email verification and trial-credit granting (docs/adr/009-email-verification-and-signup-limits.md).

Signup creates the workspace with 0 credits. Confirming the emailed link marks the user
verified and — once per workspace, atomically — grants TRIAL_EXTRACTIONS, subject to a global
daily cap that acts as a spend circuit breaker.
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from jose import JWTError
from prisma.models import User

from app.core.config import get_settings
from app.core.db import db
from app.core.email import send_verification_email
from app.core.security import create_verification_token, decode_verification_token

logger = logging.getLogger("app.services.email_verification")


async def send_verification(user: User) -> bool:
    """Email `user` a fresh verification link. Never raises (see core.email.send_email)."""
    token = create_verification_token(user.id, user.email)
    link = f"{get_settings().FRONTEND_URL.rstrip('/')}/verify-email?token={token}"
    return await send_verification_email(user.email, user.name, link)


async def verify_email(token: str) -> int:
    """
    Confirm an emailed token. Idempotent: re-opening the link is a harmless no-op.
    Returns the number of trial extractions granted by THIS call (0 if none).
    """
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This verification link is invalid or has expired. Request a new one from the dashboard.",
    )
    try:
        payload = decode_verification_token(token)
    except JWTError:
        raise invalid

    user_id, email = payload["sub"], payload["email"]
    now = datetime.now(timezone.utc)

    async with db.tx() as tx:
        user = await tx.user.find_unique(where={"id": user_id})
        if not user or not user.isActive or user.email != email:
            raise invalid
        # Conditional update: only the first confirmation proceeds to the grant.
        marked = await tx.user.update_many(
            where={"id": user_id, "emailVerifiedAt": None},
            data={"emailVerifiedAt": now},
        )
        if marked == 0:
            return 0
        return await _grant_trial(tx, user.workspaceId, now)


async def _grant_trial(tx, workspace_id: str, now: datetime) -> int:
    settings = get_settings()
    amount = settings.TRIAL_EXTRACTIONS
    if amount == 0:
        return 0

    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    granted_today = await tx.workspace.count(where={"trialGrantedAt": {"gte": day_start}})
    if granted_today >= settings.TRIAL_DAILY_GRANT_CAP:
        # Soft cap: concurrent verifications can overshoot by a few. It bounds spend, not exactly.
        logger.warning(
            "TRIAL_CAP_REACHED granted_today=%s cap=%s workspace=%s — verified without credits",
            granted_today, settings.TRIAL_DAILY_GRANT_CAP, workspace_id,
        )
        return 0

    # Guarded by trialGrantedAt IS NULL so a workspace can never be granted twice.
    granted = await tx.workspace.update_many(
        where={"id": workspace_id, "trialGrantedAt": None},
        data={"trialExtractionsRemaining": amount, "trialGrantedAt": now},
    )
    return amount if granted else 0
