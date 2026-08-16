import logging
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from prisma.models import User

from app.core.auth import get_current_user
from app.core.db import db
from app.core.security import create_access_token, generate_api_key, hash_password, verify_password
from app.models.schemas import (
    Role,
    TokenResponse,
    UserLoginRequest,
    UserResponse,
    UserSignupRequest,
    WorkspaceResponse,
)

logger = logging.getLogger("app.api.auth")
router = APIRouter()


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: UserSignupRequest) -> TokenResponse:
    """
    User Registration Endpoint.
    1. Verifies email uniqueness.
    2. Enforces presence of pre-seeded 'free' Plan in database.
    3. Creates new Workspace and User (assigned as OWNER).
    4. Issues JWT access token.
    """
    # 1. Check existing user
    existing_user = await db.user.find_unique(where={"email": payload.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    # 2. Strict Pre-flight Plan Check (Requires pre-seeded database)
    free_plan = await db.plan.find_first(where={"slug": "free"})
    if not free_plan:
        logger.error("Signup failed: 'free' Plan tier is missing from PostgreSQL database.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: Default 'free' plan not found in database. Please run 'python -m app.db.seed'.",
        )

    # 3. Create Workspace & User
    ws_name = payload.workspaceName or f"{payload.name or payload.email}'s Workspace"
    ws_slug = f"ws-{uuid4().hex[:10]}"
    hashed_pwd = hash_password(payload.password)
    api_key = generate_api_key()

    workspace = await db.workspace.create(
        data={
            "name": ws_name,
            "slug": ws_slug,
            "apiKey": api_key,
            "planId": free_plan.id,
        }
    )

    user = await db.user.create(
        data={
            "email": payload.email,
            "passwordHash": hashed_pwd,
            "name": payload.name,
            "workspaceId": workspace.id,
            "role": Role.OWNER.value,
        }
    )

    # 4. Generate Token
    access_token = create_access_token(
        data={
            "sub": user.id,
            "workspace_id": workspace.id,
            "role": user.role,
        }
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
        workspace=WorkspaceResponse.model_validate(workspace),
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLoginRequest) -> TokenResponse:
    """
    User Login Endpoint.
    Validates user credentials against stored bcrypt hash and returns JWT access token.
    """
    user = await db.user.find_unique(where={"email": payload.email})
    if not user or not user.passwordHash or not verify_password(payload.password, user.passwordHash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.isActive:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated. Contact workspace owner.",
        )

    workspace = await db.workspace.find_unique(where={"id": user.workspaceId})
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated workspace not found.",
        )

    access_token = create_access_token(
        data={
            "sub": user.id,
            "workspace_id": workspace.id,
            "role": user.role,
        }
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
        workspace=WorkspaceResponse.model_validate(workspace),
    )


@router.get("/me", response_model=TokenResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> TokenResponse:
    """
    Authenticated User Profile Endpoint.
    Returns currently logged-in user profile, role, and workspace metadata.
    """
    workspace = await db.workspace.find_unique(where={"id": current_user.workspaceId})
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        )

    # Re-issue active access token payload confirmation
    access_token = create_access_token(
        data={
            "sub": current_user.id,
            "workspace_id": workspace.id,
            "role": current_user.role,
        }
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(current_user),
        workspace=WorkspaceResponse.model_validate(workspace),
    )
