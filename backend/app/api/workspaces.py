from fastapi import APIRouter, Depends, HTTPException, status
from prisma.models import User, Workspace

from app.core.auth import get_current_user, get_current_workspace, require_role
from app.core.db import db
from app.core.security import generate_api_key
from app.models.schemas import (
    Role,
    UserResponse,
    WorkspaceRotateApiKeyResponse,
    WorkspaceUpdate,
    WorkspaceWithPlanResponse,
)

router = APIRouter()


@router.get("/current", response_model=WorkspaceWithPlanResponse)
async def get_current_workspace_details(
    workspace: Workspace = Depends(get_current_workspace),
) -> WorkspaceWithPlanResponse:
    """
    Get active workspace details and attached billing Plan.
    Accessible via Bearer token or X-API-Key header.
    """
    full_workspace = await db.workspace.find_unique(
        where={"id": workspace.id},
        include={"plan": True},
    )
    if not full_workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        )
    return WorkspaceWithPlanResponse.model_validate(full_workspace)


@router.put("/current", response_model=WorkspaceWithPlanResponse)
async def update_current_workspace(
    payload: WorkspaceUpdate,
    current_user: User = Depends(require_role(Role.OWNER)),
) -> WorkspaceWithPlanResponse:
    """
    Update workspace metadata (e.g. name).
    Restricted to workspace OWNER role.
    """
    updated_workspace = await db.workspace.update(
        where={"id": current_user.workspaceId},
        data={"name": payload.name},
        include={"plan": True},
    )
    if not updated_workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        )
    return WorkspaceWithPlanResponse.model_validate(updated_workspace)


@router.post("/current/api-key/rotate", response_model=WorkspaceRotateApiKeyResponse)
async def rotate_workspace_api_key(
    current_user: User = Depends(require_role(Role.OWNER)),
) -> WorkspaceRotateApiKeyResponse:
    """
    Regenerate workspace API Key.
    Restricted to workspace OWNER role. Invalidates existing API Key.
    """
    new_api_key = generate_api_key()
    await db.workspace.update(
        where={"id": current_user.workspaceId},
        data={"apiKey": new_api_key},
    )
    return WorkspaceRotateApiKeyResponse(apiKey=new_api_key)


@router.get("/current/members", response_model=list[UserResponse])
async def get_workspace_members(
    workspace: Workspace = Depends(get_current_workspace),
) -> list[UserResponse]:
    """
    List all active user members of the current workspace.
    """
    users = await db.user.find_many(
        where={"workspaceId": workspace.id, "isActive": True},
        order={"createdAt": "asc"},
    )
    return [UserResponse.model_validate(u) for u in users]
