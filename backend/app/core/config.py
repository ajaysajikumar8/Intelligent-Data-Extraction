from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    All values are read from backend/.env during local development.
    In production, set these via the cloud platform dashboard.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    DATABASE_URL: str

    # ------------------------------------------------------------------ #
    # Google Gemini AI
    # ------------------------------------------------------------------ #
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-3.6-flash"

    # ------------------------------------------------------------------ #
    # JWT Authentication
    # ------------------------------------------------------------------ #
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # ------------------------------------------------------------------ #
    # CORS
    # ------------------------------------------------------------------ #
    # Use plain str — AnyHttpUrl adds a trailing slash which breaks CORS origin matching.
    FRONTEND_URL: str = "http://localhost:5173"

    # ------------------------------------------------------------------ #
    # Public API base URL — used to build inbound webhook URLs shown to customers
    # ------------------------------------------------------------------ #
    API_BASE_URL: str = "http://localhost:8000"

    # ------------------------------------------------------------------ #
    # Google OAuth (optional — required only from Phase 3 onwards)
    # ------------------------------------------------------------------ #
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None

    # ------------------------------------------------------------------ #
    # SendGrid Inbound Parse (optional — ECDSA signature verification)
    # ------------------------------------------------------------------ #
    SENDGRID_WEBHOOK_PUBLIC_KEY: str | None = None


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached singleton Settings instance.
    Use as a FastAPI dependency: Depends(get_settings)
    """
    return Settings()
