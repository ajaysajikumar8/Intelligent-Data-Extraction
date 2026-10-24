"""
ai_access.py — Decide which Gemini key an extraction job runs on.

One place owns the policy, so every ingestion path (dashboard, API key, inbound
adapters) behaves identically. In priority order:

  1. The workspace's own key (BYOAK).
  2. The platform key, if the workspace opted into Platform Key Fallback (paid plans).
  3. The platform key on a free-trial credit (see docs/adr/008-free-trial-credits.md).
  4. Nothing — the job fails with NO_AI_KEY.

A trial credit is spent with a single conditional UPDATE, so concurrent jobs can never
overspend it, and it is refunded if the job ends FAILED (a trial user must not lose
credit to a provider outage). A workspace with its own key never touches its credits.
"""

import logging
from dataclasses import dataclass

from prisma.models import Workspace

from app.core.db import db
from app.core.encryption import decrypt

logger = logging.getLogger("app.services.ai_access")


@dataclass(frozen=True)
class AiAccess:
    custom_api_key: str | None
    allow_platform_fallback: bool
    trial_credit_held: bool = False

    @property
    def key_source(self) -> str | None:
        """The `ApiKeySource` this route corresponds to (None = no usable key)."""
        if self.custom_api_key:
            return "WORKSPACE"
        if self.trial_credit_held:
            return "TRIAL_CREDIT"
        return "PLATFORM" if self.allow_platform_fallback else None


async def acquire(workspace: Workspace) -> AiAccess:
    """Resolve the key route for one job, spending a trial credit if that is what it takes."""
    if workspace.geminiApiKey:
        return AiAccess(decrypt(workspace.geminiApiKey), workspace.allowPlatformFallback)
    if workspace.allowPlatformFallback:
        return AiAccess(None, True)

    spent = await db.workspace.update_many(
        where={"id": workspace.id, "trialExtractionsRemaining": {"gt": 0}},
        data={"trialExtractionsRemaining": {"decrement": 1}},
    )
    if spent:
        return AiAccess(None, True, trial_credit_held=True)
    return AiAccess(None, False)


async def refund_trial_credit(workspace_id: str) -> None:
    """Give back a credit held by a job that failed. Best-effort: must never mask the job's outcome."""
    try:
        await db.workspace.update(
            where={"id": workspace_id},
            data={"trialExtractionsRemaining": {"increment": 1}},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not refund trial credit for workspace %s: %s", workspace_id, exc)
