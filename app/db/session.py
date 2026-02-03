from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base

_ENGINE = None
_SessionLocal = None


def init_db(database_url: str) -> None:
    global _ENGINE, _SessionLocal
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    _ENGINE = create_engine(database_url, connect_args=connect_args)
    _SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=_ENGINE,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=_ENGINE)


@contextmanager
def get_db() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized")
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
