"""Global SQLAlchemy engine/session setup used by API handlers and scripts.

Sessions are short-lived and transactional via `get_db()`. The engine/session
factory is process-global and initialized during app startup or script entry.
"""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base

_ENGINE: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_db(database_url: str) -> None:
    """Initialize the global SQLAlchemy engine and session factory."""
    global _ENGINE, _SessionLocal
    # Rationale: SQLite commonly runs under tests/local dev where access may cross
    # threads, which requires `check_same_thread=False`.
    is_sqlite = database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False, "timeout": 5} if is_sqlite else {}
    _ENGINE = create_engine(database_url, connect_args=connect_args)
    if is_sqlite:
        _configure_sqlite_pragmas(_ENGINE)
    _SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=_ENGINE,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=_ENGINE)


def get_engine() -> Engine:
    """Return the initialized engine or raise if startup has not run yet."""
    if _ENGINE is None:
        raise RuntimeError("Database not initialized")
    return _ENGINE


def _configure_sqlite_pragmas(engine: Engine) -> None:
    """Enable SQLite settings that improve write concurrency under load."""

    @event.listens_for(engine, "connect")
    def _apply_sqlite_pragmas(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()


@contextmanager
def get_db() -> Session:
    """Yield a transactional session and commit/rollback automatically."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized")
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        # Why: always rollback so callers do not continue with a failed transaction.
        db.rollback()
        raise
    finally:
        db.close()
