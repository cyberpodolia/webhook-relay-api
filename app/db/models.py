"""SQLAlchemy ORM models for persisted webhook events."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for ORM models."""

    pass


class Event(Base):
    """Inbound webhook event plus persisted relay execution metadata.

    Invariant:
        `(source, idempotency_key)` is unique when `idempotency_key` is provided.
    """

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("source", "idempotency_key", name="uq_events_source_idempotency_key"),
        Index("ix_events_received_at_id", "received_at", "id"),
        Index("ix_events_source_received_at_id", "source", "received_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID string.
    source: Mapped[str] = mapped_column(String(100), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    headers: Mapped[dict] = mapped_column(JSON)  # Sanitized subset of inbound headers.
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    # Why: idempotency is caller-provided and enforced per source via composite unique key.
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Relay columns are updated after the initial insert so intake succeeds even when relay fails.
    relay_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    relay_attempted: Mapped[int] = mapped_column(Integer, default=0)
    relay_success: Mapped[int] = mapped_column(Integer, default=0)
    relay_attempts: Mapped[int] = mapped_column(Integer, default=0)
    relay_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    relay_last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    relay_last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relay_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
