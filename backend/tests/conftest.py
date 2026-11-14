from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def static_dir(tmp_path_factory):
    """Demo data for two targets, built with the real pipeline code on synthetic exposures."""
    from pipeline.targets import load_targets
    from scripts.make_mock_static import build_target

    root = tmp_path_factory.mktemp("static")
    work = tmp_path_factory.mktemp("fits")
    targets = load_targets()
    for tid in ("wise0855", "rdra"):
        build_target(targets[tid], root / "fields", work)
    return root


@pytest.fixture()
def client(static_dir, monkeypatch):
    monkeypatch.setenv("STATIC_DIR", str(static_dir))
    for var in ("DATABASE_URL", "MODEL_PATH", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    from app.deps import reset_caches
    from app.main import create_app

    reset_caches()
    yield TestClient(create_app())
    reset_caches()
