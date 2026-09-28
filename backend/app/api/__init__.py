from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.inbound import router as inbound_router
from app.api.ingest import router as ingest_router
from app.api.logs import router as logs_router
from app.api.templates import router as templates_router
from app.api.webhooks import router as webhooks_router
from app.api.workspaces import router as workspaces_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router,      prefix="/auth",      tags=["Authentication"])
api_router.include_router(workspaces_router, prefix="/workspaces", tags=["Workspaces"])
api_router.include_router(templates_router,  prefix="/templates",  tags=["Templates"])
api_router.include_router(ingest_router,     prefix="/ingest",     tags=["Ingestion"])
api_router.include_router(webhooks_router,   prefix="/webhooks",   tags=["Webhooks"])
api_router.include_router(logs_router,       prefix="/logs",       tags=["Audit Logs"])
# Inbound adapters: no /api/v1 prefix auth — workspace resolved via URL secret
api_router.include_router(inbound_router,    prefix="/inbound",    tags=["Inbound Adapters"])
