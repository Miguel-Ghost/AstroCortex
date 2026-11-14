"""Targets, field manifests, classified sources and catalog layers (contracts 7.1-7.4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.config import Settings, get_settings
from app.deps import get_predictor, get_store
from app.errors import ApiError
from app.schemas import CLASSES, CatalogsResponse, FieldManifest, SourcesResponse, Target
from app.services.classifier import Predictor, sort_candidates_first
from app.services.static_store import StaticStore

router = APIRouter(prefix="/api", tags=["fields"])


@router.get("/targets", response_model=list[Target])
def list_targets(store: StaticStore = Depends(get_store)) -> list[dict]:
    return store.list_targets()


@router.get("/field", response_model=FieldManifest)
def get_field(
    target_id: str | None = Query(None, max_length=50),
    ra: float | None = Query(None, ge=0, lt=360),
    dec: float | None = Query(None, ge=-90, le=90),
    fov_arcmin: float = Query(3.0, gt=0),
    store: StaticStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    if fov_arcmin > settings.max_fov_arcmin:
        raise ApiError(422, "fov_too_large", f"fov_arcmin must be <= {settings.max_fov_arcmin}")
    if target_id is None:
        if ra is None or dec is None:
            raise ApiError(422, "missing_position", "Give target_id or both ra and dec")
        target_id = store.find_target_near(ra, dec, settings.target_match_arcmin)
    manifest = store.manifest(target_id) if target_id else None
    if manifest is not None:
        return manifest
    # TODO(Brian): live fields -> run the pipeline for (ra, dec) with a small cap of exposures and a timeout.
    raise ApiError(404, "field_not_available",
                   "This version serves the 5 test targets; live fields for any coordinate are not ready yet")


@router.get("/sources", response_model=SourcesResponse)
def get_sources(
    field_id: str = Query(..., max_length=100),
    store: StaticStore = Depends(get_store),
    predictor: Predictor = Depends(get_predictor),
    settings: Settings = Depends(get_settings),
) -> dict:
    raw = store.read_json(field_id, "sources.json")
    if raw is None:
        raise ApiError(404, "sources_not_available", f"No sources for field '{field_id}'")
    rows = raw["sources"] if isinstance(raw, dict) else raw
    sources = [{**row, **predictor.predict(row.get("evidence", {}))} for row in rows]
    manifest = store.manifest(field_id) or {}
    return {
        "field_id": field_id,
        "method": predictor.method,
        "model_version": predictor.version,
        "pipeline_commit": manifest.get("pipeline_commit", settings.commit),
        "data_release": manifest.get("data_release", settings.data_release),
        "synthetic": bool(isinstance(raw, dict) and raw.get("synthetic")),
        "calibrated": predictor.calibrated,
        "classes": list(CLASSES),
        "thresholds": predictor.thresholds,
        "rule_params": predictor.rule_params,
        "sources": sort_candidates_first(sources),
    }


@router.get("/catalogs", response_model=CatalogsResponse)
def get_catalogs(field_id: str = Query(..., max_length=100), store: StaticStore = Depends(get_store)) -> dict:
    raw = store.read_json(field_id, "catalogs.json")
    if raw is None:
        raise ApiError(404, "catalogs_not_available", f"No catalog layers for field '{field_id}'")
    return {"field_id": field_id, **raw}
