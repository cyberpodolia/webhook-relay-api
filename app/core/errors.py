"""Shared error response helpers and exception handlers for the API layer."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    """Build the standard JSON error envelope used by this service."""
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=payload)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Convert framework HTTP exceptions into the service's error schema."""
    code = (
        str(exc.detail).lower().replace(" ", "_") if isinstance(exc.detail, str) else "http_error"
    )
    return error_response(exc.status_code, code, str(exc.detail))


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return validation failures in a stable machine-readable format."""
    return error_response(422, "validation_error", "Request validation failed", exc.errors())
