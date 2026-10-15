from fastapi import APIRouter, Depends, HTTPException, status
from prisma.models import User, Workspace

from app.core.auth import get_current_user, get_current_workspace, require_role
from app.core.db import db
from app.core.encryption import encrypt
from app.core.security import generate_api_key
from app.models.schemas import (
    GeminiKeyUpdate,
    GeminiKeyUpdateResponse,
    PlatformFallbackUpdate,
    Role,
    UserResponse,
    WorkspaceRotateApiKeyResponse,
    WorkspaceUpdate,
    WorkspaceWithPlanResponse,
)
from app.services import gemini_service

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


@router.put("/current/gemini-key", response_model=GeminiKeyUpdateResponse)
async def save_gemini_key(
    payload: GeminiKeyUpdate,
    current_user: User = Depends(require_role(Role.OWNER)),
) -> GeminiKeyUpdateResponse:
    """
    Validate and save the workspace's custom Gemini API key (BYOAK).
    Restricted to workspace OWNER role.

    The key is verified with a live, lightweight Gemini call before being
    encrypted (Fernet, ENCRYPTION_KEY) and written to the database — this
    catches typos/revoked keys at save time instead of at extraction time.
    """
    try:
        await gemini_service.validate_api_key(payload.apiKey)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    await db.workspace.update(
        where={"id": current_user.workspaceId},
        data={"geminiApiKey": encrypt(payload.apiKey)},
    )
    return GeminiKeyUpdateResponse()


@router.delete("/current/gemini-key", response_model=WorkspaceWithPlanResponse)
async def delete_gemini_key(
    current_user: User = Depends(require_role(Role.OWNER)),
) -> WorkspaceWithPlanResponse:
    """
    Remove the workspace's custom Gemini API key.
    Restricted to workspace OWNER role. Extractions fall back to the
    platform key logic governed by `allowPlatformFallback`.
    """
    updated_workspace = await db.workspace.update(
        where={"id": current_user.workspaceId},
        data={"geminiApiKey": None},
        include={"plan": True},
    )
    return WorkspaceWithPlanResponse.model_validate(updated_workspace)


@router.put("/current/platform-fallback", response_model=WorkspaceWithPlanResponse)
async def set_platform_fallback(
    payload: PlatformFallbackUpdate,
    current_user: User = Depends(require_role(Role.OWNER)),
) -> WorkspaceWithPlanResponse:
    """
    Toggle the Platform Key Fallback kill switch.
    Restricted to workspace OWNER role.

    Enabling it is explicit consent to be billed for platform Gemini usage
    when the workspace's own key (if any) hits quota — so it requires an
    active paid plan. Disabling it is always allowed.
    """
    if payload.enabled:
        workspace = await db.workspace.find_unique(
            where={"id": current_user.workspaceId},
            include={"plan": True},
        )
        if not workspace or not workspace.plan or workspace.plan.priceUsdCents <= 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Platform Key Fallback requires a paid plan. Upgrade to enable this.",
            )

    updated_workspace = await db.workspace.update(
        where={"id": current_user.workspaceId},
        data={"allowPlatformFallback": payload.enabled},
        include={"plan": True},
    )
    return WorkspaceWithPlanResponse.model_validate(updated_workspace)


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
