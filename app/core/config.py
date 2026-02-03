from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    app_host: str
    app_port: int
    database_url: str
    target_url: str
    log_level: str


@lru_cache
def get_settings() -> Settings:
    app_host = os.getenv("APP_HOST", "0.0.0.0")
    app_port = int(os.getenv("APP_PORT", "8000"))
    database_url = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    target_url = os.getenv("TARGET_URL", "").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")

    return Settings(
        app_host=app_host,
        app_port=app_port,
        database_url=database_url,
        target_url=target_url,
        log_level=log_level,
    )
