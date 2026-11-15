"""User marks and votes (contract 7.7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.deps import get_marks_repo, get_store
from app.errors import ApiError
from app.schemas import MarkIn, MarkOut
from app.services.static_store import StaticStore

router = APIRouter(prefix="/api", tags=["marks"])


def _canonical(store: StaticStore, field_id: str) -> str:
    """Votes are stored under the manifest's field_id, whatever name the client used (BR-FIELD-06)."""
    ref = store.resolve(field_id)
    if ref is None:
        raise ApiError(404, "field_not_found", f"Unknown field '{field_id}'.")
    return ref.field_id


@router.post("/marks", response_model=MarkOut, status_code=201)
def add_mark(mark: MarkIn, repo=Depends(get_marks_repo), store: StaticStore = Depends(get_store)) -> dict:
    return repo.add({**mark.model_dump(), "field_id": _canonical(store, mark.field_id)})


@router.get("/marks", response_model=list[MarkOut])
def list_marks(
    field_id: str = Query(..., max_length=100), repo=Depends(get_marks_repo), store: StaticStore = Depends(get_store)
) -> list[dict]:
    return repo.list(_canonical(store, field_id))
