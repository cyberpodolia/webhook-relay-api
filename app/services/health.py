from __future__ import annotations

from sqlalchemy import text

from app.db.session import get_db


def check_db() -> None:
    with get_db() as db:
        db.execute(text("SELECT 1"))
