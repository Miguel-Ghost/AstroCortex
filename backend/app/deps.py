"""Shared objects, created once per process (FastAPI dependencies; tests can override them)."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.services.classifier import Predictor, load_predictor
from app.services.marks_repo import make_marks_repo
from app.services.static_store import StaticStore


@lru_cache
def get_store() -> StaticStore:
    s = get_settings()
    return StaticStore(s.fields_dir, s.targets_file)


@lru_cache
def get_predictor() -> Predictor:
    return load_predictor(get_settings().model_path)


@lru_cache
def get_marks_repo():
    return make_marks_repo(get_settings().database_url)


@lru_cache
def get_live_fields():
    from app.services.live import LiveFields

    return LiveFields(get_settings())


def reset_caches() -> None:
    for fn in (get_settings, get_store, get_predictor, get_marks_repo, get_live_fields):
        fn.cache_clear()
