from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.workspaces import router as workspaces_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(workspaces_router, prefix="/workspaces", tags=["Workspaces"])
