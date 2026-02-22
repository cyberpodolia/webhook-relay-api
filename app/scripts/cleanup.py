"""CLI entrypoint for retention cleanup (cron-friendly wrapper)."""

from __future__ import annotations

import sys

from app.core.config import get_settings
from app.db.session import init_db
from app.services.cleanup import cleanup_old_events


def main() -> int:
    """Run event cleanup using environment configuration.

    Returns:
        int: process exit code (`0` success, `2` when retention is not configured).
    """
    settings = get_settings()
    init_db(settings.database_url)
    if settings.event_retention_days is None:
        # Rationale: explicit non-zero exit makes cron/systemd failures visible.
        print("EVENT_RETENTION_DAYS is not set", file=sys.stderr)
        return 2
    deleted = cleanup_old_events(settings.event_retention_days)
    print(f"Deleted {deleted} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
