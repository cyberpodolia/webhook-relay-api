"""HTTP API routes for webhook intake, event retrieval, and admin cleanup.

Routes in this module validate inbound requests, persist events, optionally relay
events outbound, and return normalized Pydantic response models.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query, Request
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.logging import request_id_ctx
from app.core.security import enforce_body_size_limit, require_admin_token, verify_webhook_signature
from app.db.models import Event
from app.db.session import get_db
from app.metrics import EVENTS_RECEIVED_TOTAL
from app.schemas import (
    CleanupResponse,
    CreateWebhookResponse,
    EventItem,
    EventsListResponse,
    HealthResponse,
)
from app.services import relay
from app.services.cleanup import cleanup_old_events

router = APIRouter()
logger = logging.getLogger("app.api")


def _safe_headers(request: Request) -> dict[str, str]:
    """Return the small header subset we intentionally persist/relay."""
    headers = {}
    for key in ["user-agent", "content-type", "x-request-id"]:
        value = request.headers.get(key)
        if value:
            headers[key] = value
    return headers


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize datetimes to timezone-aware UTC for API serialization."""
    if value is None:
        return None
    # Edge case: SQLite may return naive datetimes despite timezone-aware columns.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _event_relay_result(event: Event) -> dict[str, Any] | None:
    """Map persisted relay columns into the public relay response shape."""
    if event.relay_status is None:
        return None
    return {
        "attempted": bool(event.relay_attempted),
        "success": bool(event.relay_success),
        "reason": event.relay_reason,
        "status_code": event.relay_last_status_code,
        "attempts": event.relay_attempts or 0,
        "last_error": event.relay_last_error,
        "last_attempt_at": _as_utc(event.relay_last_attempt_at),
    }


def _event_item(event: Event) -> EventItem:
    """Convert an `Event` ORM row into the list/get response schema."""
    return EventItem(
        event_id=event.id,
        source=event.source,
        received_at=_as_utc(event.received_at),
        payload=event.payload,
        headers=event.headers,
        request_id=event.request_id,
        idempotency_key=event.idempotency_key,
        relay=_event_relay_result(event),
    )


def _create_response(event: Event) -> CreateWebhookResponse:
    """Build the create webhook response, including persisted relay result state."""
    return CreateWebhookResponse(
        event_id=event.id,
        received_at=_as_utc(event.received_at),
        relay=_event_relay_result(event),
    )


def _encode_cursor(received_at: datetime, event_id: str) -> str:
    """Encode pagination state as an opaque base64 cursor."""
    payload = {"ts": _as_utc(received_at).isoformat(), "id": event_id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Decode and validate an opaque cursor.

    Raises:
        HTTPException: 400 when the cursor is malformed.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        ts = datetime.fromisoformat(payload["ts"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc), str(payload["id"])
    except Exception as exc:  # noqa: BLE001
        # Security: cursor content is untrusted input; return a stable client
        # error instead of leaking parser/decoder internals.
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe: the process can accept HTTP requests."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    """Readiness probe: verifies DB connectivity before returning OK."""
    from app.services.health import check_db

    check_db()
    return HealthResponse(status="ok")


@router.post("/webhooks/{source}", response_model=CreateWebhookResponse)
async def create_event(source: str, request: Request) -> CreateWebhookResponse:
    """Accept a webhook, persist it, and optionally relay to the configured target.

    If `Idempotency-Key` is provided and already exists for the same source, this
    returns the original event response instead of creating a duplicate.
    """
    settings = get_settings()
    if settings.allowed_sources and source not in settings.allowed_sources:
        # Security: return 404 to avoid confirming whether a source name exists.
        raise HTTPException(status_code=404, detail="Not found")

    raw_body = await request.body()
    # Security: validate size and signature against the raw bytes before JSON parsing.
    enforce_body_size_limit(raw_body, settings.max_body_bytes)
    verify_webhook_signature(
        raw_body, request.headers.get("X-Webhook-Signature"), settings.webhook_secret
    )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Invalid JSON body") from exc
    if not isinstance(payload, dict):
        # Invariant: only JSON objects are stored to keep response shape stable.
        raise HTTPException(status_code=422, detail="Payload must be a JSON object")

    request_id = request_id_ctx.get() or str(uuid4())
    idempotency_key = request.headers.get("Idempotency-Key")
    safe_headers = {**_safe_headers(request), "x-request-id": request_id}

    if idempotency_key:
        with get_db() as db:
            existing = db.execute(
                select(Event).where(
                    and_(Event.source == source, Event.idempotency_key == idempotency_key)
                )
            ).scalar_one_or_none()
        if existing is not None:
            # Rationale: duplicates must not create another row or trigger another relay.
            return _create_response(existing)

    received_at = datetime.now(timezone.utc)
    event = Event(
        id=str(uuid4()),
        source=source,
        received_at=received_at,
        payload=payload,
        headers=safe_headers,
        request_id=request_id,
        idempotency_key=idempotency_key,
    )

    try:
        with get_db() as db:
            db.add(event)
    except IntegrityError:
        if not idempotency_key:
            raise
        # Edge case: handle concurrent inserts racing on the unique idempotency key.
        with get_db() as db:
            existing = db.execute(
                select(Event).where(
                    and_(Event.source == source, Event.idempotency_key == idempotency_key)
                )
            ).scalar_one_or_none()
        if existing is None:
            raise
        return _create_response(existing)

    EVENTS_RECEIVED_TOTAL.labels(source=source).inc()
    logger.info("event_received", extra={"source": source, "event_id": event.id})

    if settings.target_url:
        relay_result = await relay.relay_event(
            event={
                "event_id": event.id,
                "source": source,
                "received_at": event.received_at.astimezone(timezone.utc).isoformat(),
                "payload": payload,
                "headers": safe_headers,
            },
            target_url=settings.target_url,
            request_id=request_id,
            relay_allow_hosts=settings.relay_allow_hosts,
        )
        with get_db() as db:
            stored = db.get(Event, event.id)
            if stored is not None:
                # Rationale: relay result is persisted after intake so webhook
                # acceptance is not coupled to relay success.
                stored.relay_status = "success" if relay_result.get("success") else "failed"
                if not relay_result.get("attempted"):
                    stored.relay_status = "skipped"
                stored.relay_attempted = 1 if relay_result.get("attempted") else 0
                stored.relay_success = 1 if relay_result.get("success") else 0
                stored.relay_attempts = int(relay_result.get("attempts") or 0)
                stored.relay_reason = relay_result.get("reason")
                stored.relay_last_error = relay_result.get("last_error")
                stored.relay_last_status_code = relay_result.get("status_code")
                stored.relay_last_attempt_at = relay_result.get("last_attempt_at")
                event = stored

    return _create_response(event)


@router.get("/events", response_model=EventsListResponse)
async def list_events(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    source: str | None = None,
) -> EventsListResponse:
    """List events with source filtering and opaque cursor pagination."""
    stmt = select(Event)
    if source:
        stmt = stmt.where(Event.source == source)
    if cursor:
        cursor_ts, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Event.received_at < cursor_ts,
                # Rationale: tie-break by ID to make pagination deterministic.
                and_(Event.received_at == cursor_ts, Event.id < cursor_id),
            )
        )
    # Perf: fetch one extra row to determine `next_cursor` without a separate count.
    stmt = stmt.order_by(Event.received_at.desc(), Event.id.desc()).limit(limit + 1)

    with get_db() as db:
        rows = db.execute(stmt).scalars().all()

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = None
    if has_more and items:
        tail = items[-1]
        next_cursor = _encode_cursor(tail.received_at, tail.id)

    return EventsListResponse(events=[_event_item(e) for e in items], next_cursor=next_cursor)


@router.get("/events/{event_id}", response_model=EventItem)
async def get_event(event_id: str) -> EventItem:
    """Fetch a single stored event by primary key."""
    with get_db() as db:
        event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_item(event)


@router.post("/admin/cleanup", response_model=CleanupResponse)
async def admin_cleanup(x_admin_token: str | None = Header(default=None)) -> CleanupResponse:
    """Delete events older than retention; guarded by an admin token.

    Raises:
        HTTPException: 401/403 for auth failures, 400 when retention is not set.
    """
    settings = get_settings()
    require_admin_token(x_admin_token, settings.admin_token)
    if settings.event_retention_days is None:
        raise HTTPException(status_code=400, detail="EVENT_RETENTION_DAYS is not set")
    return CleanupResponse(deleted_count=cleanup_old_events(settings.event_retention_days))
