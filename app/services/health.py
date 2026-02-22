"""Health/readiness checks used by probe endpoints."""

from __future__ import annotations

from sqlalchemy import text

from app.db.session import get_db


def check_db() -> None:
    """Execute a trivial query to verify the DB session/connection path works."""
    with get_db() as db:
        db.execute(text("SELECT 1"))
