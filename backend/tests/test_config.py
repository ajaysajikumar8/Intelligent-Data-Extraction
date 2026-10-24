"""
test_config.py — Production startup checks (APP_ENV=production refuses unsafe settings).
"""

import logging

import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings


def _settings(**overrides: object) -> Settings:
    """A fully valid production configuration, with overrides. Ignores any local .env file."""
    values: dict[str, object] = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql://u:p@db.internal:5432/app",
        "GEMINI_API_KEY": "real-looking-gemini-key",
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "SECRET_KEY": "x" * 48,
        "FRONTEND_URL": "https://app.example.com",
        "API_BASE_URL": "https://api.example.com",
        "RESEND_API_KEY": "re_live_key",
        "EMAIL_FROM": "App <noreply@example.com>",
        "TRUSTED_PROXY_HOPS": 1,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_valid_production_config_starts():
    assert _settings().APP_ENV == "production"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"ENCRYPTION_KEY": None}, "ENCRYPTION_KEY is not set"),
        ({"ENCRYPTION_KEY": "your-fernet-key-here"}, "not a valid Fernet key"),
        ({"SECRET_KEY": "short"}, "SECRET_KEY"),
        ({"SECRET_KEY": "your-secret-key-change-in-production-32-chars-minimum"}, "SECRET_KEY"),
        ({"GEMINI_API_KEY": "your-gemini-api-key-here"}, "GEMINI_API_KEY"),
        ({"WEBHOOK_ALLOW_PRIVATE_HOSTS": True}, "WEBHOOK_ALLOW_PRIVATE_HOSTS"),
        ({"FRONTEND_URL": "http://localhost:5178"}, "FRONTEND_URL still points at localhost"),
        ({"API_BASE_URL": "http://api.example.com"}, "API_BASE_URL must use https"),
        ({"RESEND_API_KEY": None}, "RESEND_API_KEY"),
        ({"EMAIL_FROM": "App <onboarding@resend.dev>"}, "EMAIL_FROM"),
    ],
)
def test_unsafe_production_config_is_refused(overrides: dict, expected: str):
    with pytest.raises(ValueError, match="Refusing to start") as exc:
        _settings(**overrides)
    assert expected in str(exc.value)


def test_all_problems_are_reported_at_once_and_secrets_are_not_echoed():
    with pytest.raises(ValueError) as exc:
        _settings(SECRET_KEY="your-secret-key-change-in-production", RESEND_API_KEY=None, ENCRYPTION_KEY=None)
    message = str(exc.value)
    assert "SECRET_KEY" in message and "RESEND_API_KEY" in message and "ENCRYPTION_KEY" in message
    assert "your-secret-key-change-in-production" not in message


def test_warnings_do_not_block_startup(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        _settings(TRUSTED_PROXY_HOPS=0, SIGNUP_LIMIT_PER_IP_PER_HOUR=50)
    text = caplog.text
    assert "TRUSTED_PROXY_HOPS is 0" in text
    assert "Signup rate limits are above their defaults" in text


def test_development_is_not_checked():
    s = _settings(APP_ENV="development", ENCRYPTION_KEY=None, SECRET_KEY="dev", FRONTEND_URL="http://localhost:5178", RESEND_API_KEY=None)
    assert s.APP_ENV == "development"


def test_hosted_platform_without_app_env_warns(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    monkeypatch.setenv("RENDER", "true")
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        _settings(APP_ENV="development")
    assert "Set APP_ENV=production" in caplog.text


def test_validation_errors_do_not_echo_the_raw_settings():
    with pytest.raises(ValueError) as exc:
        _settings(FRONTEND_URL="http://localhost:5178", DATABASE_URL="postgresql://dbuser:hunter2-password@db/app")
    assert "hunter2-password" not in str(exc.value) and "input_value" not in str(exc.value)
