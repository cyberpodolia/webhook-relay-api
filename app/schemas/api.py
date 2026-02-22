"""Pydantic API response schemas.

These models define the external contract returned by route handlers and hide
internal ORM details where the public field names differ.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RelayResult(BaseModel):
    """Relay attempt/result metadata returned to API clients."""

    attempted: bool
    success: bool
    reason: str | None = None
    status_code: int | None = None
    attempts: int = 0  # Number of outbound attempts that actually ran.
    last_error: str | None = None
    last_attempt_at: datetime | None = None  # UTC timestamp of final attempt.


class EventItem(BaseModel):
    """Event record as returned by list/get endpoints."""

    model_config = ConfigDict(extra="ignore")

    event_id: str
    source: str
    received_at: datetime
    payload: dict[str, Any]
    headers: dict[str, Any]  # Sanitized subset of inbound request headers.
    request_id: str
    idempotency_key: str | None = None
    relay: RelayResult | None = None


class CreateWebhookResponse(BaseModel):
    """Response body for webhook intake (create or idempotent replay)."""

    event_id: str
    received_at: datetime
    relay: RelayResult | None = None


class EventsListResponse(BaseModel):
    """Paginated list response with an opaque `next_cursor`."""

    events: list[EventItem]
    next_cursor: str | None = None


class HealthResponse(BaseModel):
    """Simple liveness/readiness probe payload."""

    status: str


class CleanupResponse(BaseModel):
    """Admin cleanup result with count of deleted events."""

    deleted_count: int


class ErrorBody(BaseModel):
    """Inner error payload returned in `ErrorResponse`."""

    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    """Top-level error response envelope."""

    error: ErrorBody
