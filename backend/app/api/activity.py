"""
activity.py — Workspace activity log (who changed what).

  GET /api/v1/activity   Newest first. Workspace OWNERs only: the log includes sign-in IP addresses
                         and security events. Filter by `category` (see services/activity.py).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from prisma.models import User

from app.core.auth import require_role
from app.core.db import db
from app.models.schemas import ActivityLogResponse, Role
from app.services.activity import ACTION_CATEGORIES

router = APIRouter()


@router.get("", response_model=list[ActivityLogResponse])
async def list_activity(
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    category: str | None = Query(None, description=f"One of: {', '.join(ACTION_CATEGORIES)}"),
    current_user: User = Depends(require_role(Role.OWNER)),
) -> list[ActivityLogResponse]:
    where: dict = {"workspaceId": current_user.workspaceId}
    if category is not None:
        prefixes = ACTION_CATEGORIES.get(category)
        if prefixes is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown category. Use one of: {', '.join(ACTION_CATEGORIES)}.",
            )
        where["OR"] = [{"action": {"startswith": p}} for p in prefixes]

    rows = await db.activitylog.find_many(
        where=where,  # type: ignore[arg-type]
        skip=skip,
        take=limit,
        order=[{"createdAt": "desc"}, {"id": "desc"}],
    )
    return [ActivityLogResponse.model_validate(r) for r in rows]
