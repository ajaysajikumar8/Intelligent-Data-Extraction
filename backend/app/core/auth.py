from fastapi import Depends, HTTPException, Header, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from prisma.models import User, Workspace

from app.core.db import db
from app.core.security import decode_access_token
from app.models.schemas import Role

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(token: str | None = Depends(oauth2_scheme)) -> User:
    """
    FastAPI dependency that extracts and verifies Bearer JWT token,
    loading the active User object from the database.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials or token expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await db.user.find_unique(where={"id": user_id})
    if not user or not user.isActive:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account deactivated.",
        )
    return user


async def get_current_workspace(
    token: str | None = Depends(oauth2_scheme),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> Workspace:
    """
    Dual-mode authentication dependency.
    Resolves active Workspace via EITHER:
    1. X-API-Key header (for automated REST API integrations)
    2. Bearer JWT token (for interactive Next.js dashboard users)
    """
    # 1. API Key Header Authentication
    if x_api_key:
        workspace = await db.workspace.find_unique(
            where={"apiKey": x_api_key},
            include={"plan": True},
        )
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API Key.",
            )
        return workspace

    # 2. Bearer JWT Token Authentication
    if token:
        user = await get_current_user(token)
        workspace = await db.workspace.find_unique(
            where={"id": user.workspaceId},
            include={"plan": True},
        )
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace associated with user not found.",
            )
        return workspace

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide a Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(required_role: Role):
    """
    Role-Based Access Control (RBAC) dependency factory.
    Enforces minimum role level for sensitive workspace operations.
    """
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action requires '{required_role.value}' role.",
            )
        return current_user

    return role_checker
