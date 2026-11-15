"""Targets, field manifests, classified sources and catalog layers (contracts 7.1-7.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.deps import get_predictor, get_store
from app.errors import ApiError
from app.schemas import CatalogsResponse, SourcesResponse, Target
from app.services.classifier import Predictor
from app.services.engine import classify_field
from app.services.static_store import StaticStore
from app.static_files import CACHE_CONTROL

router = APIRouter(prefix="/api", tags=["fields"])


@router.get("/targets", response_model=list[Target])
def list_targets(store: StaticStore = Depends(get_store)) -> list[dict]:
    return store.list_targets()


@router.get("/field", responses={200: {"description": "The field's manifest.json, unchanged"}})
def get_field(
    ra: float | None = Query(None, ge=0, lt=360),
    dec: float | None = Query(None, ge=-90, le=90),
    fov_arcmin: float | None = Query(None, gt=0),  # accepted and ignored: the published field has its own size
    target_id: str | None = Query(None, max_length=50),
    store: StaticStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """The manifest of the field whose centre is within 1 arcmin of (ra, dec), returned as it is on disk.

    The frontend reads the manifest's field names as they are, so it is not re-serialised through a
    schema that could rename, drop or add fields.
    """
    if target_id is None:
        if ra is None or dec is None:
            raise ApiError(400, "bad_request", "ra and dec are required.")
        target_id = store.find_target_near(ra, dec, settings.target_match_arcmin)
    manifest = store.manifest(target_id) if target_id else None
    if manifest is None:
        raise ApiError(404, "no_coverage", "No SPHEREx images cover this position yet.")
    return JSONResponse(content=manifest, headers={"Cache-Control": CACHE_CONTROL})


@router.get("/sources", response_model=SourcesResponse)
def get_sources(
    field_id: str = Query(..., max_length=100),
    store: StaticStore = Depends(get_store),
    predictor: Predictor = Depends(get_predictor),
    settings: Settings = Depends(get_settings),
) -> dict:
    result = classify_field(field_id, store, predictor, settings)
    if result is None:
        raise ApiError(404, "sources_not_available", f"No sources for field '{field_id}'")
    return result


@router.get("/catalogs", response_model=CatalogsResponse)
def get_catalogs(field_id: str = Query(..., max_length=100), store: StaticStore = Depends(get_store)) -> dict:
    raw = store.read_json(field_id, "catalogs.json")
    if raw is None:
        raise ApiError(404, "catalogs_not_available", f"No catalog layers for field '{field_id}'")
    return {"field_id": field_id, **raw}
