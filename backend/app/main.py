import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import Settings, get_settings
from app.core.db import db, connect_db, disconnect_db

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI Lifespan Context Manager.
    Handles startup (DB connect & pre-flight seed check) and shutdown (DB disconnect) tasks.
    """
    await connect_db()

    # Pre-flight guard: Verify database has been seeded with required Plan tiers
    free_plan = await db.plan.find_first(where={"slug": "free"})
    if not free_plan:
        msg = (
            "CRITICAL: Database has not been seeded with required Plan tiers! "
            "Run 'python -m app.db.seed' before starting the application."
        )
        logger.critical(msg)
        raise RuntimeError(msg)

    logger.info("Pre-flight database seed check passed (Free plan ID: %s).", free_plan.id)
    yield
    await disconnect_db()



app = FastAPI(
    title="Intelligent Data Extraction API",
    description="AI-powered document ingestion and structured data extraction service.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# --------------------------------------------------------------------------- #
# CORS Middleware
# --------------------------------------------------------------------------- #
def _configure_cors(application: FastAPI, settings: Settings) -> None:
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(settings.FRONTEND_URL)],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


_configure_cors(app, get_settings())


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
app.include_router(api_router)


@app.get("/health", tags=["System"])
async def health_check(settings: Settings = Depends(get_settings)) -> dict:
    """
    Liveness and readiness probe endpoint.
    Returns service status, environment, and DB connectivity status.
    """
    db_connected = db.is_connected()
    return {
        "status": "ok" if db_connected else "degraded",
        "service": "intelligent-data-extraction",
        "version": app.version,
        "environment": "development" if "localhost" in str(settings.FRONTEND_URL) else "production",
        "database": "connected" if db_connected else "disconnected",
    }

