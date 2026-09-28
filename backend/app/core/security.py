import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    """
    Hash a plain text password using bcrypt (truncated to 72 bytes max as required by bcrypt).
    """
    password_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain text password against its bcrypt hash.
    """
    password_bytes = plain_password.encode("utf-8")[:72]
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """
    Create a JWT access token containing claims (sub, workspace_id, role).
    """
    settings = get_settings()
    to_encode = data.copy()

    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT access token.
    Raises JWTError if invalid or expired.
    """
    settings = get_settings()
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    return payload


def generate_api_key() -> str:
    """
    Generate a secure random UUID string for workspace API keys.
    """
    return str(uuid.uuid4())


def generate_inbound_secret() -> str:
    """
    Generate a cryptographically unguessable secret token for inbound webhook URLs.

    The token is embedded in the URL path:
        POST /api/v1/inbound/{inboundSecret}

    Using 32 random bytes (256-bit entropy) encoded as hex, making it
    virtually impossible to brute-force or guess.
    """
    import secrets
    return secrets.token_hex(32)


def hmac_sign(secret: str, payload: bytes) -> str:
    """
    Compute an HMAC-SHA256 signature of `payload` using `secret`.

    Used for two purposes:
      1. Outbound webhook delivery: we sign the JSON payload we send to
         customer servers so they can verify it came from us.
      2. Inbound provider verification: we re-compute the provider's
         HMAC signature (e.g. Mailgun) to verify the request is genuine.

    Returns a hex-encoded signature string.
    """
    import hashlib
    import hmac as _hmac
    return _hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
