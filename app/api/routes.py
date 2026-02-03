from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import request_id_ctx
from app.db.models import Event
from app.db.session import get_db
from app.services import relay

router = APIRouter()
logger = logging.getLogger("app.api")


def _safe_headers(request: Request) -> Dict[str, str]:
    headers = {}
    for key in ["user-agent", "content-type", "x-request-id"]:
        value = request.headers.get(key)
        if value:
            headers[key] = value
    return headers


@router.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> Dict[str, str]:
    from app.services.health import check_db

    check_db()
    return {"status": "ok"}


@router.post("/webhooks/{source}")
async def create_event(
    source: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    settings = get_settings()
    request_id = request_id_ctx.get() or str(uuid4())
    received_at = datetime.now(timezone.utc)
    event_id = str(uuid4())

    event = Event(
        id=event_id,
        source=source,
        received_at=received_at,
        payload=payload,
        headers={**_safe_headers(request), "x-request-id": request_id},
        request_id=request_id,
    )

    with get_db() as db:
        db.add(event)

    logger.info("event_received", extra={"source": source, "event_id": event_id})

    relay_result: dict[str, Any] | None = None
    if settings.target_url:
        relay_result = await relay.relay_event(
            event={
                "event_id": event_id,
                "source": source,
                "received_at": received_at.isoformat(),
                "payload": payload,
                "headers": {**_safe_headers(request), "x-request-id": request_id},
            },
            target_url=settings.target_url,
            request_id=request_id,
        )

    response = {
        "event_id": event_id,
        "received_at": received_at.isoformat(),
    }
    if relay_result is not None:
        response["relay"] = relay_result
    return response


@router.get("/events")
async def list_events(limit: int = 50) -> Dict[str, Any]:
    limit = min(max(limit, 1), 100)
    with get_db() as db:
        events = db.execute(select(Event).order_by(Event.received_at.desc()).limit(limit)).scalars().all()

    return {
        "events": [
            {
                "event_id": e.id,
                "source": e.source,
                "received_at": e.received_at.isoformat(),
                "payload": e.payload,
                "headers": e.headers,
                "request_id": e.request_id,
            }
            for e in events
        ]
    }


@router.get("/events/{event_id}")
async def get_event(event_id: str) -> Dict[str, Any]:
    with get_db() as db:
        event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return {
        "event_id": event.id,
        "source": event.source,
        "received_at": event.received_at.isoformat(),
        "payload": event.payload,
        "headers": event.headers,
        "request_id": event.request_id,
    }
