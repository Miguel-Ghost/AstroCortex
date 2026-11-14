"""User marks and votes (contract 7.7)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.deps import get_marks_repo
from app.schemas import MarkIn, MarkOut

router = APIRouter(prefix="/api", tags=["marks"])


@router.post("/marks", response_model=MarkOut, status_code=201)
def add_mark(mark: MarkIn, repo=Depends(get_marks_repo)) -> dict:
    return repo.add(mark.model_dump())


@router.get("/marks", response_model=list[MarkOut])
def list_marks(field_id: str = Query(..., max_length=100), repo=Depends(get_marks_repo)) -> list[dict]:
    return repo.list(field_id)
