"""
encryption.py — Symmetric encryption wrapper for sensitive workspace settings.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package.

The ENCRYPTION_KEY env var must be a URL-safe base64-encoded 32-byte key.
Generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

If ENCRYPTION_KEY is not set, values are stored as plaintext with a warning.
This allows zero-config local development while strongly encouraging encryption
in any production deployment.
"""

import logging

logger = logging.getLogger("app.core.encryption")


def _get_fernet():
    """Return a Fernet instance if ENCRYPTION_KEY is configured, else None."""
    # Import here to avoid circular import with config
    from app.core.config import get_settings
    settings = get_settings()
    if not settings.ENCRYPTION_KEY:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(settings.ENCRYPTION_KEY.encode())
    except Exception as e:
        logger.error("Invalid ENCRYPTION_KEY — cannot initialise Fernet: %s", e)
        return None


def encrypt(value: str) -> str:
    """
    Encrypt a string value for database storage.

    Returns encrypted ciphertext as a UTF-8 string.
    Falls back to storing the original value as plaintext if ENCRYPTION_KEY
    is not configured (logs a warning so it's obvious in dev logs).
    """
    fernet = _get_fernet()
    if fernet is None:
        logger.warning(
            "ENCRYPTION_KEY not set — storing sensitive value as plaintext. "
            "Set ENCRYPTION_KEY in backend/.env for any production deployment."
        )
        return value
    return fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """
    Decrypt a previously encrypted string back to plaintext.

    Falls back to returning the value as-is if ENCRYPTION_KEY is not set
    (handles the case where the value was stored as plaintext in local dev).
    """
    fernet = _get_fernet()
    if fernet is None:
        return value  # Was stored as plaintext — return directly
    try:
        return fernet.decrypt(value.encode()).decode()
    except Exception:
        # Decryption failed — value may have been stored as plaintext (migration path)
        logger.warning(
            "Fernet decryption failed — returning value as plaintext. "
            "This is expected when migrating from a plaintext storage setup."
        )
        return value
