import logging
import os
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

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
        # Validation errors must never echo the raw settings (they contain secrets such as the database URL).
        hide_input_in_errors=True,
    )

    # ------------------------------------------------------------------ #
    # Environment. "production" turns on startup safety checks (see `production_problems`):
    # the app refuses to start with placeholder secrets, no encryption key, no email setup, etc.
    # Set APP_ENV=production on every real deployment.
    # ------------------------------------------------------------------ #
    APP_ENV: Literal["development", "production"] = "development"

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
    # Signup abuse protection (see docs/adr/009-email-verification-and-signup-limits.md).
    # Trial credits are granted when the email is verified, not at signup. Rate limits are
    # in-process (per instance) like the extraction queue; swap for a shared store if scaled out.
    # ------------------------------------------------------------------ #
    # Max credit grants per UTC day across the platform — a spend circuit breaker. 0 = grant none.
    TRIAL_DAILY_GRANT_CAP: int = Field(default=50, ge=0)
    SIGNUP_LIMIT_PER_IP_PER_HOUR: int = Field(default=5, ge=1)
    # Non-mainstream email domains only (gmail.com etc. are exempt — see core/signup_guard.py).
    SIGNUP_LIMIT_PER_DOMAIN_PER_HOUR: int = Field(default=3, ge=1)
    VERIFICATION_RESEND_LIMIT_PER_HOUR: int = Field(default=3, ge=1)
    VERIFICATION_TOKEN_EXPIRE_HOURS: int = Field(default=24, ge=1)
    # How many reverse proxies sit in front of the app (Render/Railway = 1). The client IP is
    # taken from that many entries from the RIGHT of X-Forwarded-For; 0 ignores the header.
    # Never raise this above the real hop count — the left side of the header is client-forged.
    TRUSTED_PROXY_HOPS: int = Field(default=0, ge=0, le=5)

    # ------------------------------------------------------------------ #
    # Outbound email (Resend). With no key set, emails are logged instead of sent (local dev).
    # EMAIL_FROM must be on a domain verified in Resend, e.g. "App <noreply@yourdomain.com>".
    # ------------------------------------------------------------------ #
    RESEND_API_KEY: str | None = None
    EMAIL_FROM: str = "Intelligent Data Extraction <onboarding@resend.dev>"

    # ------------------------------------------------------------------ #
    # Extraction queue (in-process — see docs/adr/006-async-extraction-queue.md)
    # Limits are per process. Queued jobs hold uploaded file bytes in memory,
    # so the backlog is capped: roughly MAX_BACKLOG × the 20 MB upload limit.
    # ------------------------------------------------------------------ #
    EXTRACTION_MAX_CONCURRENCY: int = 4
    EXTRACTION_MAX_BACKLOG: int = 50
    EXTRACTION_JOB_TIMEOUT_SECONDS: int = 450
    # Per-workspace cap on documents queued or running, so one tenant's batch
    # cannot fill the shared backlog. Set to 0 to disable.
    EXTRACTION_MAX_IN_FLIGHT_PER_WORKSPACE: int = 25

    # ------------------------------------------------------------------ #
    # Activity log (see docs/adr/015-activity-log.md). Entries older than this are deleted at
    # startup. 0 keeps them forever.
    # ------------------------------------------------------------------ #
    ACTIVITY_RETENTION_DAYS: int = Field(default=365, ge=0)

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
    FRONTEND_URL: str = "http://localhost:5178"

    # ------------------------------------------------------------------ #
    # Outbound webhooks — SSRF protection (see app/core/url_safety.py).
    # By default customer webhook URLs must resolve to PUBLIC addresses only. Set true
    # in local development to deliver to localhost; never in production.
    # ------------------------------------------------------------------ #
    WEBHOOK_ALLOW_PRIVATE_HOSTS: bool = False

    # ------------------------------------------------------------------ #
    # Public API base URL — used to build inbound webhook URLs shown to customers
    # ------------------------------------------------------------------ #
    API_BASE_URL: str = "http://localhost:8005"

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

        if self.APP_ENV == "production":
            errors, warnings = production_problems(self)
            for warning in warnings:
                logger.warning("Production check: %s", warning)
            if errors:
                raise ValueError(
                    "Refusing to start with APP_ENV=production. Fix these settings:\n  - "
                    + "\n  - ".join(errors)
                )
        else:
            if not self.ENCRYPTION_KEY or not self.ENCRYPTION_KEY.strip():
                logger.warning(
                    "ENCRYPTION_KEY is not set — BYOAK Gemini keys will be stored as "
                    "plaintext. Fine for local dev; set it before any production deployment."
                )
            if any(os.environ.get(var) for var in _HOSTED_PLATFORM_ENV_VARS):
                logger.warning(
                    "This looks like a hosted platform but APP_ENV is not 'production', so the "
                    "production safety checks are skipped. Set APP_ENV=production."
                )

        return self


# Environment variables hosted platforms set on their runtimes; used only to warn about a missing APP_ENV.
_HOSTED_PLATFORM_ENV_VARS = ("RENDER", "RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "FLY_APP_NAME", "VERCEL")

# Defaults of the signup limits; a higher value in production usually means a leftover QA setting.
_DEFAULT_SIGNUP_LIMIT_PER_IP = 5
_DEFAULT_SIGNUP_LIMIT_PER_DOMAIN = 3


def _is_local_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or host.endswith(".localhost")


def production_problems(s: "Settings") -> tuple[list[str], list[str]]:
    """
    Settings that are unsafe or broken for a real deployment.

    Returns (errors, warnings). Errors make startup fail when APP_ENV=production: each one is a
    misconfiguration that silently breaks signup, weakens security, or exposes customer secrets.
    Warnings are logged. Values themselves are never included in messages.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not s.ENCRYPTION_KEY or not s.ENCRYPTION_KEY.strip():
        errors.append("ENCRYPTION_KEY is not set: customers' own Gemini keys would be stored unencrypted.")
    else:
        try:
            from cryptography.fernet import Fernet

            Fernet(s.ENCRYPTION_KEY.encode())
        except Exception:  # noqa: BLE001 — any failure means the key is unusable
            errors.append(
                "ENCRYPTION_KEY is not a valid Fernet key "
                "(generate one: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\")."
            )

    secret = s.SECRET_KEY.strip()
    if len(secret) < 32 or "change-in-production" in secret.lower() or secret.lower().startswith("your-"):
        errors.append("SECRET_KEY is a placeholder or shorter than 32 characters: anyone could forge login tokens.")

    if s.GEMINI_API_KEY.strip().lower().startswith("your-"):
        errors.append("GEMINI_API_KEY is still the example placeholder.")

    if s.WEBHOOK_ALLOW_PRIVATE_HOSTS:
        errors.append("WEBHOOK_ALLOW_PRIVATE_HOSTS must be false: it disables the SSRF protection (ADR-007).")

    for name in ("FRONTEND_URL", "API_BASE_URL"):
        url = getattr(s, name)
        if _is_local_url(url):
            errors.append(f"{name} still points at localhost.")
        elif not url.lower().startswith("https://"):
            errors.append(f"{name} must use https.")

    if not s.RESEND_API_KEY or not s.RESEND_API_KEY.strip():
        errors.append("RESEND_API_KEY is not set: verification emails would only be logged, so nobody could verify or get trial credits.")
    elif "resend.dev" in s.EMAIL_FROM.lower():
        errors.append("EMAIL_FROM uses Resend's shared test sender, which only delivers to your own address. Use a verified domain.")

    if s.TRUSTED_PROXY_HOPS == 0:
        warnings.append(
            "TRUSTED_PROXY_HOPS is 0: behind a reverse proxy (Render/Railway = 1) every user shares the proxy's IP "
            "and the per-IP signup limit throttles everyone together."
        )
    if s.SIGNUP_LIMIT_PER_IP_PER_HOUR > _DEFAULT_SIGNUP_LIMIT_PER_IP or s.SIGNUP_LIMIT_PER_DOMAIN_PER_HOUR > _DEFAULT_SIGNUP_LIMIT_PER_DOMAIN:
        warnings.append("Signup rate limits are above their defaults (leftover QA values?).")

    return errors, warnings


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached singleton Settings instance.
    Use as a FastAPI dependency: Depends(get_settings)
    """
    return Settings()
