from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl
from functools import lru_cache


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

    # ------------------------------------------------------------------ #
    # JWT Authentication
    # ------------------------------------------------------------------ #
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # ------------------------------------------------------------------ #
    # CORS
    # ------------------------------------------------------------------ #
    FRONTEND_URL: AnyHttpUrl = "http://localhost:3000"  # type: ignore[assignment]

    # ------------------------------------------------------------------ #
    # Google OAuth (optional — required only from Phase 3 onwards)
    # ------------------------------------------------------------------ #
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached singleton Settings instance.
    Use as a FastAPI dependency: Depends(get_settings)
    """
    return Settings()
