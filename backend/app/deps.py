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
def get_llm():
    """The language-model client, or None when LLM_API_KEY or LLM_MODEL is missing."""
    s = get_settings()
    if not (s.llm_api_key and s.llm_model):
        return None
    from app.services.llm import LLMClient

    return LLMClient(
        s.llm_api_key, s.llm_base_url, s.llm_model, s.llm_fallback_models, s.llm_timeout_s, s.llm_json_mode
    )


@lru_cache
def get_agent_limits():
    from app.services.ratelimit import AgentLimits

    s = get_settings()
    return AgentLimits(s.agent_rpm_per_ip, s.llm_rpm_per_ip, s.llm_rpd_per_ip, s.llm_daily_max)


@lru_cache
def get_live_fields():
    from app.services.live import LiveFields

    return LiveFields(get_settings())


def reset_caches() -> None:
    for fn in (get_settings, get_store, get_predictor, get_marks_repo, get_live_fields, get_llm, get_agent_limits):
        fn.cache_clear()
