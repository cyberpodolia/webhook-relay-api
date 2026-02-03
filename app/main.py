from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import request_id_ctx, setup_logging
from app.db.session import init_db
from app.metrics import REQUEST_COUNT, REQUEST_LATENCY


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    init_db(settings.database_url)

    app = FastAPI(title="Webhook Relay API")
    app.include_router(router)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        req_id = request.headers.get("x-request-id") or str(uuid4())
        request_id_ctx.set(req_id)

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        path = request.url.path
        REQUEST_COUNT.labels(request.method, path, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(duration)

        logging.getLogger("app.request").info(
            "request",
            extra={
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )

        response.headers["X-Request-ID"] = req_id
        return response

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logging.getLogger("app.error").exception(
            "unhandled_exception",
            extra={"path": request.url.path, "method": request.method},
        )
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    logging.getLogger("app.main").info("app_started")
    return app


app = create_app()
