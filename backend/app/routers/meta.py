"""Service status and declared engines."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.config import get_settings
from app.deps import get_marks_repo, get_predictor, get_store
from app.domain.vocab import REVIEW_REASON_TEXT
from app.schemas import Health, Meta

router = APIRouter(tags=["meta"])
log = logging.getLogger("api")


@router.get("/health", response_model=Health)
def health() -> dict:
    """Checks its dependencies for real; any failure answers "degraded" instead of a false "ok"."""
    settings = get_settings()
    checks: dict[str, bool] = {}
    model_version, method = "unavailable", "unavailable"
    try:
        predictor = get_predictor()
        model_version, method = predictor.version, predictor.method
        checks["classifier"] = True
    except Exception:  # noqa: BLE001
        log.exception("classifier failed to load")
        checks["classifier"] = False
    try:
        static_fields = len(get_store().fields())
    except Exception:  # noqa: BLE001
        log.exception("static store unavailable")
        static_fields = 0
    checks["static_fields"] = static_fields > 0
    try:
        checks["marks"] = get_marks_repo().ping()
    except Exception:  # noqa: BLE001
        log.exception("marks storage unavailable")
        checks["marks"] = False
    return {
        "status": "ok" if all(checks.values()) else "degraded",
        "commit": settings.commit,
        "model_version": model_version,
        "classifier_method": method,
        "checks": checks,
        "static_fields": static_fields,
    }


@router.get("/api/meta", response_model=Meta)
def meta() -> dict:
    settings = get_settings()
    predictor = get_predictor()
    repo = get_marks_repo()
    return {
        "app": "AstroCortex",
        "version": settings.app_version,
        "commit": settings.commit,
        "data_release": settings.data_release,
        "classifier": {"method": predictor.method, "version": predictor.version, "calibrated": predictor.calibrated},
        "marks": {"storage": repo.storage, "persistent": repo.persistent},
        "live_fields": settings.live_fields,
        "review_reasons": {str(k): v for k, v in REVIEW_REASON_TEXT.items()},
    }
