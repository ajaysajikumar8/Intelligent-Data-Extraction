"""
gemini_service.py — Async wrapper around Google Gemini 1.5 Flash.

Responsibilities:
  - Initialise the Gemini client once from GEMINI_API_KEY.
  - Provide a simple `generate_text` method for plain-text prompts.
  - Provide a `generate_with_file` method for inline binary content
    (PDF / PNG / JPEG passed as base64-encoded bytes).
  - All public methods return a plain string — callers are responsible
    for JSON-parsing the result.
"""

import base64
import logging
from functools import lru_cache

import google.generativeai as genai

from app.core.config import get_settings

logger = logging.getLogger("app.services.gemini")

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
MODEL_NAME = "gemini-1.5-flash"
GENERATION_CONFIG = genai.types.GenerationConfig(
    temperature=0.1,         # Low temperature → deterministic, structured output
    top_p=0.95,
    max_output_tokens=4096,
)


@lru_cache(maxsize=1)
def _get_model() -> genai.GenerativeModel:
    """
    Singleton Gemini model instance.
    Configured once on first call; cached for the process lifetime.
    """
    settings = get_settings()
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        generation_config=GENERATION_CONFIG,
    )


async def generate_text(prompt: str) -> str:
    """
    Send a plain-text prompt to Gemini and return the response text.

    Args:
        prompt: The full prompt string to send.

    Returns:
        Gemini's response as a stripped string.

    Raises:
        RuntimeError: If Gemini returns an empty or blocked response.
    """
    model = _get_model()
    logger.debug("Sending text prompt to Gemini (%d chars)", len(prompt))

    response = await model.generate_content_async(prompt)

    if not response.text:
        raise RuntimeError(
            "Gemini returned an empty response. "
            "The request may have been blocked by safety filters."
        )

    logger.debug("Received Gemini response (%d chars)", len(response.text))
    return response.text.strip()


async def generate_with_file(
    prompt: str,
    file_bytes: bytes,
    mime_type: str,
) -> str:
    """
    Send a multimodal prompt to Gemini with an inline binary file
    (PDF, PNG, or JPEG) and return the response text.

    The file is passed as inline base64-encoded data — no external
    upload to Google File API required for files under ~20 MB.

    Args:
        prompt:     The instruction/question to accompany the file.
        file_bytes: Raw bytes of the file.
        mime_type:  MIME type string, e.g. "application/pdf", "image/png".

    Returns:
        Gemini's response as a stripped string.

    Raises:
        RuntimeError: If Gemini returns an empty or blocked response.
    """
    model = _get_model()
    logger.debug(
        "Sending multimodal prompt to Gemini (file: %d bytes, mime: %s)",
        len(file_bytes),
        mime_type,
    )

    inline_data = {
        "inline_data": {
            "mime_type": mime_type,
            "data": base64.b64encode(file_bytes).decode("utf-8"),
        }
    }

    response = await model.generate_content_async([prompt, inline_data])

    if not response.text:
        raise RuntimeError(
            "Gemini returned an empty response for the file input. "
            "The request may have been blocked by safety filters."
        )

    logger.debug("Received Gemini multimodal response (%d chars)", len(response.text))
    return response.text.strip()
