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
    static_dir: Path = field(default_factory=lambda: Path(os.getenv("STATIC_DIR", ROOT / "data" / "static")))
    targets_file: Path = field(default_factory=lambda: Path(os.getenv("TARGETS_FILE", ROOT / "data" / "targets.json")))
    cors_origins: list[str] = field(default_factory=lambda: _csv(os.getenv("CORS_ORIGINS", "http://localhost:5173")))
    cors_origin_regex: str | None = field(default_factory=lambda: os.getenv("CORS_ORIGIN_REGEX") or None)
    database_url: str | None = field(default_factory=lambda: os.getenv("DATABASE_URL") or None)
    model_path: Path | None = field(default_factory=lambda: Path(p) if (p := os.getenv("MODEL_PATH")) else None)
    data_release: str = field(default_factory=lambda: os.getenv("DATA_RELEASE", "spherex_dr1"))
    commit: str = field(default_factory=lambda: os.getenv("RENDER_GIT_COMMIT", "dev")[:7])
    llm_api_key: str | None = field(default_factory=lambda: os.getenv("LLM_API_KEY") or None)
    max_fov_arcmin: float = field(default_factory=lambda: float(os.getenv("MAX_FOV_ARCMIN", "5")))
    target_match_arcmin: float = field(default_factory=lambda: float(os.getenv("TARGET_MATCH_ARCMIN", "3")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_json: bool = field(default_factory=lambda: os.getenv("LOG_JSON", "true").lower() == "true")
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "0.2.0"))

    @property
    def fields_dir(self) -> Path:
        return self.static_dir / "fields"


@lru_cache
def get_settings() -> Settings:
    return Settings()
