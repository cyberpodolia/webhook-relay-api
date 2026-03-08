"""Application entrypoint and FastAPI assembly.

This module wires the router, middleware, exception handlers, database startup,
and shared relay HTTP client lifecycle. Major side effects are DB initialization,
metrics emission, and logging for every request.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.core.config import get_settings
from app.core.errors import error_response, http_exception_handler, validation_exception_handler
from app.core.logging import request_id_ctx, setup_logging
from app.db.session import init_db
from app.metrics import REQUEST_COUNT, REQUEST_LATENCY
from app.services.relay import (
    shutdown_http_client,
    shutdown_relay_dispatcher,
    startup_http_client,
    startup_relay_dispatcher,
)


def _label_path(request: Request) -> str:
    """Return a normalized path label for metrics cardinality control."""
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        # Rationale: use templated route paths (for example `/events/{event_id}`)
        # so Prometheus labels do not grow with per-resource IDs.
        return str(route.path)
    return request.url.path


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and tear down process-wide resources for the ASGI app."""
    settings = get_settings()
    setup_logging(settings.log_level)
    init_db(settings.database_url)
    await startup_http_client()
    await startup_relay_dispatcher(
        worker_count=settings.relay_worker_concurrency,
        queue_size=settings.relay_queue_size,
    )
    logging.getLogger("app.main").info("app_started")
    try:
        yield
    finally:
        await shutdown_relay_dispatcher()
        await shutdown_http_client()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(title="Webhook Relay API", lifespan=lifespan)
    app.include_router(router)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        """Propagate a request ID and record request metrics/logging."""
        req_id = request.headers.get("x-request-id") or str(uuid4())
        request_id_ctx.set(req_id)

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        path_label = _label_path(request)
        REQUEST_COUNT.labels(request.method, path_label, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.method, path_label).observe(duration)

        logging.getLogger("app.request").info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "path_label": path_label,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )

        response.headers["X-Request-ID"] = req_id
        return response

    @app.get("/metrics")
    def metrics() -> Response:
        """Expose Prometheus metrics in text format for scraping."""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Security: log full details server-side but return a generic message to
        # avoid leaking implementation details to clients.
        logging.getLogger("app.error").exception(
            "unhandled_exception",
            extra={"path": request.url.path, "method": request.method},
        )
        return error_response(500, "internal_server_error", "Internal Server Error")

    return app


app = create_app()
