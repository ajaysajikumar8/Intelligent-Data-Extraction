"""
gemini_service.py — Async wrapper around Google Gemini.

Architecture — BYOAK (Bring Your Own API Key)
---------------------------------------------
This service uses the `google-genai` SDK which supports proper per-client
API key instances. Each unique API key gets its own `genai.Client` object,
cached in a module-level dict. This avoids the global-state race condition
present in the older `google-generativeai` SDK.

Key resolution (used by the extraction pipeline):
  1. `api_key` parameter (workspace's custom BYOAK key, already decrypted)
  2. `settings.GEMINI_API_KEY` (platform key) — if `api_key` is None

All public functions accept an optional `api_key: str | None` parameter.
If None, the platform key from settings is used automatically.
"""

import logging
from functools import lru_cache

from google import genai
from google.genai import types

from app.core.config import get_settings

logger = logging.getLogger("app.services.gemini")


class EmptyGeminiResponse(RuntimeError):
    """Gemini returned no text, typically because the request was blocked by safety filters."""

# ---------------------------------------------------------------------------
# Generation config — applied to all requests
# ---------------------------------------------------------------------------
GENERATION_CONFIG = types.GenerateContentConfig(
    temperature=0.1,        # Low → deterministic, structured output
    top_p=0.95,
    max_output_tokens=4096,
)

# ---------------------------------------------------------------------------
# Per-key client cache: api_key_string → genai.Client
# Each workspace key (and the platform key) gets its own client instance.
# ---------------------------------------------------------------------------
_client_cache: dict[str, genai.Client] = {}


def _get_client(api_key: str | None = None) -> genai.Client:
    """
    Return a cached genai.Client for the given API key.
    Falls back to the platform key from settings if api_key is None.
    """
    settings = get_settings()
    key = api_key or settings.GEMINI_API_KEY
    if key not in _client_cache:
        _client_cache[key] = genai.Client(api_key=key)
        logger.debug("Created new Gemini client (key prefix: %s...)", key[:8])
    return _client_cache[key]


def _model_name(model: str | None = None) -> str:
    """The model to call: an explicit override (e.g. the backup model) or the configured primary."""
    return model or get_settings().GEMINI_MODEL


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_text(prompt: str, api_key: str | None = None, model: str | None = None) -> str:
    """
    Send a plain-text prompt to Gemini and return the response text.

    Args:
        prompt:  The full prompt string to send.
        api_key: Optional workspace BYOAK key. Uses platform key if None.

    Returns:
        Gemini's response as a stripped string.

    Raises:
        EmptyGeminiResponse: If Gemini returns an empty or blocked response.
    """
    client = _get_client(api_key)
    logger.debug("Sending text prompt to Gemini (%d chars)", len(prompt))

    response = await client.aio.models.generate_content(
        model=_model_name(model),
        contents=prompt,
        config=GENERATION_CONFIG,
    )

    if not response.text:
        raise EmptyGeminiResponse(
            "Gemini returned an empty response. "
            "The request may have been blocked by safety filters."
        )

    logger.debug("Received Gemini response (%d chars)", len(response.text))
    return response.text.strip()


async def generate_with_file(
    prompt: str,
    file_bytes: bytes,
    mime_type: str,
    api_key: str | None = None,
    model: str | None = None,
) -> str:
    """
    Send a multimodal prompt to Gemini with an inline binary file
    (PDF, PNG, or JPEG) and return the response text.

    Args:
        prompt:     The instruction/question to accompany the file.
        file_bytes: Raw bytes of the file.
        mime_type:  MIME type string, e.g. "application/pdf", "image/png".
        api_key:    Optional workspace BYOAK key. Uses platform key if None.

    Returns:
        Gemini's response as a stripped string.
    """
    client = _get_client(api_key)
    logger.debug(
        "Sending multimodal prompt to Gemini (file: %d bytes, mime: %s)",
        len(file_bytes),
        mime_type,
    )

    file_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)

    response = await client.aio.models.generate_content(
        model=_model_name(model),
        contents=[prompt, file_part],
        config=GENERATION_CONFIG,
    )

    if not response.text:
        raise EmptyGeminiResponse(
            "Gemini returned an empty response for the file input. "
            "The request may have been blocked by safety filters."
        )

    logger.debug("Received Gemini multimodal response (%d chars)", len(response.text))
    return response.text.strip()


async def generate_with_text_and_file(
    prompt: str,
    text_body: str,
    file_bytes: bytes,
    mime_type: str,
    api_key: str | None = None,
    model: str | None = None,
) -> str:
    """
    Send a hybrid multimodal prompt containing BOTH a text body AND an inline
    binary file. Gemini processes both sources in a single API call.

    Args:
        prompt:     The instruction/question.
        text_body:  The text content (email body, cover letter, etc.).
        file_bytes: Raw bytes of the attached file.
        mime_type:  MIME type string, e.g. "application/pdf", "image/png".
        api_key:    Optional workspace BYOAK key. Uses platform key if None.

    Returns:
        Gemini's response as a stripped string.
    """
    client = _get_client(api_key)
    logger.debug(
        "Sending hybrid prompt to Gemini (text: %d chars, file: %d bytes, mime: %s)",
        len(text_body),
        len(file_bytes),
        mime_type,
    )

    file_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)

    # Pass [instruction_prompt, text_body, file] so Gemini sees both sources
    response = await client.aio.models.generate_content(
        model=_model_name(model),
        contents=[prompt, text_body, file_part],
        config=GENERATION_CONFIG,
    )

    if not response.text:
        raise EmptyGeminiResponse(
            "Gemini returned an empty response for the hybrid input. "
            "The request may have been blocked by safety filters."
        )

    logger.debug("Received Gemini hybrid response (%d chars)", len(response.text))
    return response.text.strip()


async def validate_api_key(api_key: str) -> None:
    """
    Validate a Gemini API key by making a lightweight count_tokens call.

    Raises:
        ValueError: With a user-friendly message if the key is invalid,
                    revoked, or lacks Gemini API access.
    """
    try:
        client = genai.Client(api_key=api_key)
        await client.aio.models.count_tokens(
            model=_model_name(),
            contents="test",
        )
    except Exception as e:
        error_str = str(e).lower()
        if any(kw in error_str for kw in ("api_key", "api key", "invalid", "401", "403", "permission", "unauthenticated")):
            raise ValueError(
                "The API key is invalid or does not have access to the Gemini API. "
                "Check that you've enabled the Gemini API in your Google Cloud project."
            )
        raise ValueError(f"Could not validate the API key: {e}")


def is_quota_error(exc: Exception) -> bool:
    """
    Return True if the exception indicates a quota / rate-limit exhaustion.
    Used by the extraction pipeline to decide whether to fall back to the
    platform key.
    """
    error_str = str(exc).lower()
    return any(kw in error_str for kw in (
        "429",
        "quota",
        "resource exhausted",
        "resourceexhausted",
        "rate limit",
        "ratelimitexceeded",
        "too many requests",
    ))
