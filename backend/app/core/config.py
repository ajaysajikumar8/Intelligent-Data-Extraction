import logging
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("app.core.config")

# Required at runtime — missing or blank values make every request fail in
# confusing ways downstream (DB connect errors, Gemini 401s, etc). Checked
# explicitly at startup so misconfiguration fails loudly and immediately
# instead of surfacing later as an unrelated-looking error.
_REQUIRED_KEYS = ("DATABASE_URL", "GEMINI_API_KEY", "SECRET_KEY")


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
    GEMINI_MODEL: str = "gemini-3.8-flash"
    # Optional backup model. When the primary model is overloaded (5xx / timeout), retries
    # switch to this one so a busy newest model degrades to a slightly older one instead of
    # failing the user. Opt-in: leave unset to disable. Must be a model this key can use
    # (e.g. one version behind GEMINI_MODEL); an unusable value is ignored at runtime.
    GEMINI_FALLBACK_MODEL: str | None = None

    # ------------------------------------------------------------------ #
    # Free trial (see docs/adr/008-free-trial-credits.md). Extractions each NEW workspace may
    # run on the platform key before it must add its own Gemini key. 0 disables the trial
    # (kill switch). Only affects signups from now on; it never re-grants existing workspaces.
    # ------------------------------------------------------------------ #
    TRIAL_EXTRACTIONS: int = Field(default=5, ge=0, le=100)

    # ------------------------------------------------------------------ #
    # Extraction queue (in-process — see docs/adr/006-async-extraction-queue.md)
    # Limits are per process. Queued jobs hold uploaded file bytes in memory,
    # so the backlog is capped: roughly MAX_BACKLOG × the 20 MB upload limit.
    # ------------------------------------------------------------------ #
    EXTRACTION_MAX_CONCURRENCY: int = 4
    EXTRACTION_MAX_BACKLOG: int = 50
    EXTRACTION_JOB_TIMEOUT_SECONDS: int = 450

    # ------------------------------------------------------------------ #
    # Encryption — Fernet key for encrypting BYOAK Gemini keys at rest
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # If unset, keys are stored as plaintext (acceptable for local dev only).
    # ------------------------------------------------------------------ #
    ENCRYPTION_KEY: str | None = None

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
    # Outbound webhooks — SSRF protection (see app/core/url_safety.py).
    # By default customer webhook URLs must resolve to PUBLIC addresses only. Set true
    # in local development to deliver to localhost; never in production.
    # ------------------------------------------------------------------ #
    WEBHOOK_ALLOW_PRIVATE_HOSTS: bool = False

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

    @model_validator(mode="after")
    def _check_required_env_vars(self) -> "Settings":
        """
        Pydantic already rejects a completely missing required field, but not
        one set to an empty/whitespace string (e.g. `GEMINI_API_KEY=`) — that
        silently passes validation and only fails later, deep in a request.
        Catch that here so a blank value is rejected the same way a missing
        one is, with every offending key reported at once.
        """
        blank = [key for key in _REQUIRED_KEYS if not getattr(self, key).strip()]
        if blank:
            raise ValueError(
                f"Required environment variable(s) are missing or blank: {', '.join(blank)}. "
                "Set them in backend/.env (local dev) or the platform dashboard (production)."
            )

        if not self.ENCRYPTION_KEY or not self.ENCRYPTION_KEY.strip():
            logger.warning(
                "ENCRYPTION_KEY is not set — BYOAK Gemini keys will be stored as "
                "plaintext. Fine for local dev; set it before any production deployment."
            )

        return self


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached singleton Settings instance.
    Use as a FastAPI dependency: Depends(get_settings)
    """
    return Settings()
