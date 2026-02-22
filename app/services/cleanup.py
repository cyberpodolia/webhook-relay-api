"""Retention cleanup service for deleting old event rows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.db.models import Event
from app.db.session import get_db


def cleanup_old_events(retention_days: int) -> int:
    """Delete events older than the retention window and return deleted row count."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    with get_db() as db:
        # Perf: issue a single set-based DELETE instead of row-by-row cleanup.
        result = db.execute(delete(Event).where(Event.received_at < cutoff))
        return int(result.rowcount or 0)
