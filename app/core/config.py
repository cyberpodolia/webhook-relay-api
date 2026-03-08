"""Environment-backed configuration loading and normalization.

Settings are read from environment variables and cached for process lifetime.
Tests clear the cache when they mutate env vars between app instances.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse


def _csv_set(value: str | None) -> set[str]:
    """Parse a comma-separated env var into a trimmed set, skipping empties."""
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean env var with safe defaults for unset/empty values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"Invalid boolean value for {name}: {raw}")


@dataclass(frozen=True)
class Settings:
    """Normalized runtime settings consumed across the app."""

    app_host: str
    app_port: int
    database_url: str
    target_url: str
    log_level: str
    webhook_secret: str
    max_body_bytes: int
    allowed_sources: frozenset[str]
    relay_allow_hosts: frozenset[str]
    relay_allow_private_ips: bool
    relay_worker_concurrency: int
    relay_queue_size: int
    event_retention_days: Optional[int]
    admin_token: str

    @property
    def target_url_host(self) -> str:
        """Extract the hostname from `target_url` (lowercased) for policy checks."""
        if not self.target_url:
            return ""
        return (urlparse(self.target_url).hostname or "").lower()


@lru_cache
def get_settings() -> Settings:
    """Read environment variables once and return a cached settings object."""
    app_host = os.getenv("APP_HOST", "0.0.0.0")
    app_port = int(os.getenv("APP_PORT", "8000"))
    database_url = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    target_url = os.getenv("TARGET_URL", "").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")
    webhook_secret = os.getenv("WEBHOOK_SECRET", "")
    max_body_bytes = int(os.getenv("MAX_BODY_BYTES", "1048576"))
    allowed_sources = frozenset(_csv_set(os.getenv("ALLOWED_SOURCES")))
    # Security: normalize hostnames so allowlist matching is case-insensitive.
    relay_allow_hosts = frozenset(host.lower() for host in _csv_set(os.getenv("RELAY_ALLOW_HOSTS")))
    relay_allow_private_ips = _env_bool("RELAY_ALLOW_PRIVATE_IPS", default=False)
    relay_worker_concurrency = max(int(os.getenv("RELAY_WORKER_CONCURRENCY", "8")), 1)
    relay_queue_size = max(int(os.getenv("RELAY_QUEUE_SIZE", "1000")), 1)
    event_retention_days_raw = os.getenv("EVENT_RETENTION_DAYS", "").strip()
    event_retention_days = int(event_retention_days_raw) if event_retention_days_raw else None
    admin_token = os.getenv("ADMIN_TOKEN", "")

    return Settings(
        app_host=app_host,
        app_port=app_port,
        database_url=database_url,
        target_url=target_url,
        log_level=log_level,
        webhook_secret=webhook_secret,
        max_body_bytes=max_body_bytes,
        allowed_sources=allowed_sources,
        relay_allow_hosts=relay_allow_hosts,
        relay_allow_private_ips=relay_allow_private_ips,
        relay_worker_concurrency=relay_worker_concurrency,
        relay_queue_size=relay_queue_size,
        event_retention_days=event_retention_days,
        admin_token=admin_token,
    )
