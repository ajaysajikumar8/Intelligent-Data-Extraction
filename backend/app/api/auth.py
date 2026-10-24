import logging
from uuid import uuid4
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from prisma.models import User

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.db import db
from app.core.signup_guard import client_ip, enforce_limit, enforce_signup_limits
from app.core.security import create_access_token, generate_api_key, generate_inbound_secret, hash_password, verify_password
from app.models.schemas import (
    ResendVerificationResponse,
    Role,
    TokenResponse,
    UserLoginRequest,
    UserResponse,
    UserSignupRequest,
    VerifyEmailRequest,
    VerifyEmailResponse,
    WorkspaceWithPlanResponse,
)
from app.services import email_verification

logger = logging.getLogger("app.api.auth")
router = APIRouter()


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: UserSignupRequest, request: Request, background_tasks: BackgroundTasks
) -> TokenResponse:
    """
    User Registration Endpoint.
    0. Blocks disposable domains and enforces per-IP / per-domain rate limits.
    1. Verifies email uniqueness.
    2. Enforces presence of pre-seeded 'free' Plan in database.
    3. Creates new Workspace (0 trial credits until the email is verified) and User (OWNER).
    4. Emails a verification link and issues a JWT access token.
    """
    enforce_signup_limits(request, payload.email)

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
            "inboundSecret": generate_inbound_secret(),
            "planId": free_plan.id,
            # Trial credits are granted on email verification, not here (ADR-009).
        },
        include={"plan": True},
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

    # 4. Verification email (after the response, so a slow mail provider never delays signup)
    background_tasks.add_task(email_verification.send_verification, user)

    # 5. Generate Token
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
        workspace=WorkspaceWithPlanResponse.model_validate(workspace),
    )


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(payload: VerifyEmailRequest) -> VerifyEmailResponse:
    """
    Confirm an emailed verification link. Unauthenticated on purpose: the link is often opened
    in a different browser than the one used to sign up. Grants the free trial exactly once.
    """
    granted = await email_verification.verify_email(payload.token)
    return VerifyEmailResponse(trialExtractionsGranted=granted)


@router.post("/resend-verification", response_model=ResendVerificationResponse)
async def resend_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
) -> ResendVerificationResponse:
    """Re-send the verification link to the signed-in user (rate limited)."""
    if current_user.emailVerifiedAt:
        return ResendVerificationResponse(status="already_verified")

    limit = get_settings().VERIFICATION_RESEND_LIMIT_PER_HOUR
    enforce_limit("resend-user", current_user.id, limit)
    enforce_limit("resend-ip", client_ip(request), limit * 3)
    background_tasks.add_task(email_verification.send_verification, current_user)
    return ResendVerificationResponse(status="sent")


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

    workspace = await db.workspace.find_unique(where={"id": user.workspaceId}, include={"plan": True})
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
        workspace=WorkspaceWithPlanResponse.model_validate(workspace),
    )


@router.get("/me", response_model=TokenResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> TokenResponse:
    """
    Authenticated User Profile Endpoint.
    Returns currently logged-in user profile, role, and workspace metadata.
    """
    workspace = await db.workspace.find_unique(where={"id": current_user.workspaceId}, include={"plan": True})
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
        workspace=WorkspaceWithPlanResponse.model_validate(workspace),
    )
