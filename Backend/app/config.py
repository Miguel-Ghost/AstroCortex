"""Settings from environment variables (set them in the Render dashboard or a local .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Settings:
    static_dir: Path = field(default_factory=lambda: Path(os.getenv("STATIC_DIR", ROOT / "static")))
    targets_file: Path = field(default_factory=lambda: Path(os.getenv("TARGETS_FILE", ROOT / "data" / "targets.json")))
    # a browser Origin never ends in "/": "https://x.vercel.app/" pasted from the address bar is normalised
    cors_origins: list[str] = field(
        default_factory=lambda: [o.rstrip("/") for o in _csv(os.getenv("CORS_ORIGINS", "http://localhost:5173"))]
    )
    cors_origin_regex: str | None = field(default_factory=lambda: os.getenv("CORS_ORIGIN_REGEX") or None)
    database_url: str | None = field(default_factory=lambda: os.getenv("DATABASE_URL") or None)
    model_path: Path | None = field(default_factory=lambda: Path(p) if (p := os.getenv("MODEL_PATH")) else None)
    data_release: str = field(default_factory=lambda: os.getenv("DATA_RELEASE", "spherex_dr1"))
    commit: str = field(default_factory=lambda: os.getenv("RENDER_GIT_COMMIT", "dev")[:7])
    # live agent: any /chat/completions endpoint compatible with OpenAI (key only here, never in the frontend)
    llm_api_key: str | None = field(default_factory=lambda: os.getenv("LLM_API_KEY") or None)
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    llm_model: str | None = field(default_factory=lambda: os.getenv("LLM_MODEL") or None)
    llm_fallback_models: list[str] = field(default_factory=lambda: _csv(os.getenv("LLM_FALLBACK_MODELS", "")))
    llm_timeout_s: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_S", "6")))
    llm_json_mode: bool = field(default_factory=lambda: os.getenv("LLM_JSON_MODE", "true").lower() == "true")
    # thinking models (Gemini 2.5+ Flash) spend seconds reasoning unless told otherwise; "" disables the hint
    llm_reasoning_effort: str = field(default_factory=lambda: os.getenv("LLM_REASONING_EFFORT", "low"))
    # /api/agent limits (BR-AGENT-04)
    agent_rpm_per_ip: int = field(default_factory=lambda: int(os.getenv("AGENT_RPM_PER_IP", "20")))
    llm_rpm_per_ip: int = field(default_factory=lambda: int(os.getenv("LLM_RPM_PER_IP", "6")))
    llm_rpd_per_ip: int = field(default_factory=lambda: int(os.getenv("LLM_RPD_PER_IP", "100")))
    llm_daily_max: int = field(default_factory=lambda: int(os.getenv("LLM_DAILY_MAX", "1000")))
    max_fov_arcmin: float = field(default_factory=lambda: float(os.getenv("MAX_FOV_ARCMIN", "5")))
    target_match_arcmin: float = field(default_factory=lambda: float(os.getenv("TARGET_MATCH_ARCMIN", "1")))
    # span of each target's proper-motion track accepted as a lookup position (BR-FIELD-05)
    track_epoch_min: float = field(default_factory=lambda: float(os.getenv("TRACK_EPOCH_MIN", "1990")))
    track_epoch_max: float = field(default_factory=lambda: float(os.getenv("TRACK_EPOCH_MAX", "2030")))
    # live fields for any RA/Dec (IRSA SIA + S3); off unless LIVE_FIELDS=true
    live_fields: bool = field(default_factory=lambda: os.getenv("LIVE_FIELDS", "false").lower() == "true")
    live_cache_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("LIVE_CACHE_DIR", Path(os.getenv("TMPDIR", "/tmp")) / "astrocortex-live")
        )
    )
    live_timeout_s: float = field(default_factory=lambda: float(os.getenv("LIVE_TIMEOUT_S", "60")))
    live_max_per_epoch_detector: int = field(default_factory=lambda: int(os.getenv("LIVE_MAX_PER_EPOCH_DETECTOR", "6")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_json: bool = field(default_factory=lambda: os.getenv("LOG_JSON", "true").lower() == "true")
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "0.2.0"))

    @property
    def fields_dir(self) -> Path:
        return self.static_dir / "fields"


@lru_cache
def get_settings() -> Settings:
    return Settings()
