"""
failures.py — Turn exceptions into stable, user-safe failure descriptions.

Raw provider errors (e.g. ``503 UNAVAILABLE. {'error': {...}}``) must never be
stored on a DocumentLog or shown to a user: they are confusing and can leak
internals. Everything that fails a document goes through `classify()`, which
returns a `Failure` with a stable machine-readable `code` and a friendly
`message`. The raw exception is logged server-side by the caller.

Stored shape (DocumentLog.validationErrors):
    {"error": "<friendly message>", "code": "<FailureCode>"}
"""

import asyncio
from dataclasses import dataclass
from enum import Enum

import httpx
from google.genai import errors as genai_errors

from app.services import gemini_service


class FailureCode(str, Enum):
    NO_AI_KEY = "NO_AI_KEY"
    AI_BUSY = "AI_BUSY"
    RATE_LIMITED = "RATE_LIMITED"
    AI_KEY_INVALID = "AI_KEY_INVALID"
    CONTENT_BLOCKED = "CONTENT_BLOCKED"
    BAD_AI_OUTPUT = "BAD_AI_OUTPUT"
    UNPROCESSABLE = "UNPROCESSABLE"
    TIMEOUT = "TIMEOUT"
    INTERRUPTED = "INTERRUPTED"
    INTERNAL = "INTERNAL"


_MESSAGES: dict[FailureCode, str] = {
    FailureCode.NO_AI_KEY: (
        "No AI key configured. Add your Gemini API key in Settings → AI Integration "
        "to keep extracting (any free trial extractions are used up), "
        "or enable Platform Key Fallback on a paid plan."
    ),
    FailureCode.AI_BUSY: (
        "The AI service is temporarily overloaded. We retried automatically but it is "
        "still busy. Please try again in a few minutes."
    ),
    FailureCode.RATE_LIMITED: (
        "The AI provider's usage limit was reached. Please try again in a few minutes."
    ),
    FailureCode.AI_KEY_INVALID: (
        "The AI provider rejected the API key. If you use your own key, check it in "
        "Settings → AI Integration."
    ),
    FailureCode.CONTENT_BLOCKED: (
        "The AI service returned no result for this document, possibly because it was "
        "blocked by a safety filter. Try different content."
    ),
    FailureCode.BAD_AI_OUTPUT: (
        "The AI returned a response we couldn't read. Please try again."
    ),
    FailureCode.UNPROCESSABLE: (
        "The AI service could not read this document. Try a different file, or paste "
        "the text instead."
    ),
    FailureCode.TIMEOUT: (
        "Processing took too long and was stopped. Please try again, or try a smaller document."
    ),
    FailureCode.INTERRUPTED: (
        "Processing was interrupted by a server restart. Please submit the document again."
    ),
    FailureCode.INTERNAL: (
        "Something went wrong while processing this document. Please try again."
    ),
}


@dataclass(frozen=True)
class Failure:
    code: FailureCode
    message: str

    def to_json(self) -> dict[str, str]:
        return {"error": self.message, "code": self.code.value}


def failure(code: FailureCode) -> Failure:
    return Failure(code=code, message=_MESSAGES[code])


def is_transient(exc: BaseException) -> bool:
    """True for errors worth retrying: provider 5xx and network-level failures."""
    if isinstance(exc, genai_errors.ServerError):
        return True
    return isinstance(exc, (httpx.TransportError, asyncio.TimeoutError))


def classify(exc: BaseException) -> Failure:
    """Map any exception to a user-safe Failure. Never exposes `str(exc)`."""
    if isinstance(exc, gemini_service.EmptyGeminiResponse):
        return failure(FailureCode.CONTENT_BLOCKED)

    if isinstance(exc, genai_errors.APIError):
        code = exc.code
        if code in (401, 403):
            return failure(FailureCode.AI_KEY_INVALID)
        if code == 429 or gemini_service.is_quota_error(exc):
            return failure(FailureCode.RATE_LIMITED)
        if code == 400:
            return failure(FailureCode.UNPROCESSABLE)
        if is_transient(exc):
            return failure(FailureCode.AI_BUSY)
        return failure(FailureCode.INTERNAL)

    if is_transient(exc):
        return failure(FailureCode.AI_BUSY)

    return failure(FailureCode.INTERNAL)
