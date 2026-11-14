"""FastAPI entry point: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.deps import get_predictor
from app.errors import install_error_handlers
from app.routers import agent, fields, marks
from app.schemas import Health


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SPHEREx Flipbook API", version="0.1.0",
                  description="Backend of the Space Apps 2026 'Planet X and SPHEREx' project.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(fields.router)
    app.include_router(marks.router)
    app.include_router(agent.router)

    settings.static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

    @app.get("/health", response_model=Health, tags=["meta"])
    def health() -> dict:
        predictor = get_predictor()
        return {"status": "ok", "commit": settings.commit, "model_version": predictor.version,
                "classifier_method": predictor.method}

    return app


app = create_app()
