"""FastAPI entry point: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.errors import install_error_handlers
from app.logging_setup import configure_logging, request_id
from app.routers import agent, fields, marks, meta

log = logging.getLogger("api")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(
        title="AstroCortex API",
        version=settings.app_version,
        description="Backend of the Space Apps 2026 'Planet X and SPHEREx' project.",
    )
    install_error_handlers(app)

    @app.middleware("http")
    async def correlate(request: Request, call_next):
        """Gives every request an id, returns it in X-Request-ID and logs one line per request."""
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id.reset(token)
        response.headers["X-Request-ID"] = rid
        log.info(
            "request served",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                "request_id": rid,
            },
        )
        return response

    # Added last so it wraps everything, error responses included (they keep their CORS headers).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.include_router(meta.router)
    app.include_router(fields.router)
    app.include_router(marks.router)
    app.include_router(agent.router)

    settings.static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
    log.info("service started", extra={"commit": settings.commit, "version": settings.app_version})
    return app


app = create_app()
