"""Targets, field manifests, classified sources and catalog layers (contracts 7.1-7.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.deps import get_live_fields, get_predictor, get_store
from app.errors import ApiError
from app.schemas import CatalogsResponse, SourcesResponse, Target
from app.services.classifier import Predictor
from app.services.engine import classify_field
from app.services.static_store import FieldMatch, FieldRef, StaticStore
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
    target_id: str | None = Query(None, max_length=100),  # also a field_id, a name or an alias
    store: StaticStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """The manifest of the field found for (ra, dec), returned exactly as it is on disk.

    Published fields first (BR-FIELD-05); with LIVE_FIELDS=true any other position gets a field
    built from the SPHEREx archive on request (X-Field-Match: live).

    The frontend reads the manifest's field names as they are, so it is not re-serialised through a
    schema that could rename, drop or add fields. How the field was found travels in headers
    (exposed by CORS), so the manifest stays untouched:
      X-Field-Match         center | track | target
      X-Field-Match-Epoch   Julian year of the nearest point of the target's track (track only)
      X-Field-Offset-Arcmin distance from the requested position to the field centre
      X-Target-Id           target of the field
    """
    if target_id is not None:
        ref = store.resolve(target_id)
        match = FieldMatch(ref.target_id or ref.folder, "target", None, None) if ref else None
    else:
        if ra is None or dec is None:
            raise ApiError(400, "bad_request", "ra and dec are required.")
        match = store.locate(ra, dec, settings.target_match_arcmin, settings.track_epoch_min, settings.track_epoch_max)
        if match is None and settings.live_fields:
            manifest = get_live_fields().get(ra, dec)
            return JSONResponse(
                content=manifest,
                headers={"Cache-Control": CACHE_CONTROL, "X-Field-Match": "live", "X-Field-Offset-Arcmin": "0.00"},
            )
    manifest = store.manifest(match.target_id) if match else None
    if manifest is None:
        raise ApiError(404, "no_coverage", "No SPHEREx images cover this position yet.")
    headers = {"Cache-Control": CACHE_CONTROL, "X-Field-Match": match.by, "X-Target-Id": match.target_id}
    if match.epoch is not None:
        headers["X-Field-Match-Epoch"] = f"{match.epoch:.1f}"
    if match.offset_arcmin is not None:
        headers["X-Field-Offset-Arcmin"] = f"{match.offset_arcmin:.2f}"
    return JSONResponse(content=manifest, headers=headers)


@router.get("/sources", response_model=SourcesResponse)
def get_sources(
    field_id: str = Query(..., max_length=100),
    store: StaticStore = Depends(get_store),
    predictor: Predictor = Depends(get_predictor),
    settings: Settings = Depends(get_settings),
) -> dict:
    ref = _field_or_404(store, field_id)
    result = classify_field(ref.field_id, store, predictor, settings)
    if result is None:
        raise ApiError(404, "sources_not_available", f"No sources for field '{ref.field_id}' yet.")
    return result


@router.get("/catalogs", response_model=CatalogsResponse)
def get_catalogs(field_id: str = Query(..., max_length=100), store: StaticStore = Depends(get_store)) -> dict:
    ref = _field_or_404(store, field_id)
    raw = store.read_json(ref.field_id, "catalogs.json")
    if raw is None:
        raise ApiError(404, "catalogs_not_available", f"No catalog layers for field '{ref.field_id}' yet.")
    return {**raw, "field_id": ref.field_id}


def _field_or_404(store: StaticStore, field_id: str) -> FieldRef:
    ref = store.resolve(field_id)
    if ref is None:
        raise ApiError(404, "field_not_found", f"Unknown field '{field_id}'.")
    return ref
