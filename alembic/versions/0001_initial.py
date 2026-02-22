"""initial events table"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Invariant: `(source, idempotency_key)` uniqueness is the database-level
    # enforcement for idempotent webhook intake.
    op.create_table(
        "events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("relay_status", sa.String(length=32), nullable=True),
        sa.Column("relay_attempted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("relay_success", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("relay_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("relay_reason", sa.String(length=64), nullable=True),
        sa.Column("relay_last_error", sa.String(length=500), nullable=True),
        sa.Column("relay_last_status_code", sa.Integer(), nullable=True),
        sa.Column("relay_last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "idempotency_key", name="uq_events_source_idempotency_key"),
    )
    op.create_index("ix_events_idempotency_key", "events", ["idempotency_key"], unique=False)
    op.create_index("ix_events_received_at", "events", ["received_at"], unique=False)
    op.create_index("ix_events_request_id", "events", ["request_id"], unique=False)
    op.create_index("ix_events_source", "events", ["source"], unique=False)
    # Perf: composite indexes support stable cursor pagination and filtered listing.
    op.create_index("ix_events_received_at_id", "events", ["received_at", "id"], unique=False)
    op.create_index(
        "ix_events_source_received_at_id", "events", ["source", "received_at", "id"], unique=False
    )


def downgrade() -> None:
    """Drop schema objects created by `upgrade()` in reverse dependency order."""
    op.drop_index("ix_events_source_received_at_id", table_name="events")
    op.drop_index("ix_events_received_at_id", table_name="events")
    op.drop_index("ix_events_source", table_name="events")
    op.drop_index("ix_events_request_id", table_name="events")
    op.drop_index("ix_events_received_at", table_name="events")
    op.drop_index("ix_events_idempotency_key", table_name="events")
    op.drop_table("events")
