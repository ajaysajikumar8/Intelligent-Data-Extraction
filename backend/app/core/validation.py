from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _friendly_message(error: dict[str, Any]) -> str:
    """Plain-language text for common validation failures; falls back to pydantic's message."""
    msg = str(error.get("msg", "Invalid value"))
    field = str(error["loc"][-1]) if error.get("loc") else ""
    kind = error.get("type", "")

    if field == "email":
        if "special-use or reserved" in msg:
            return "This email domain can't receive mail. Please use a real email address."
        return "Please enter a valid email address."
    if kind == "string_too_short" and field == "password":
        return "Password must be at least 8 characters."
    if kind == "string_too_long":
        return "This value is too long."
    if kind == "missing":
        return "This field is required."
    return msg.removeprefix("Value error, ")


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Same shape as FastAPI's default 422 (`detail` = list with `loc`, `msg`, `type`) so existing
    clients keep working, but with human-readable `msg` and no internal `ctx`/`input` echo.
    """
    detail = [
        {"loc": list(e.get("loc", ())), "msg": _friendly_message(e), "type": e.get("type", "")}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})
