from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _make_client(monkeypatch, static_dir=None, keep_llm=False, rule=False):
    """The API with a clean environment: no database and, unless keep_llm, no LLM key. The classifier is the bundled
    engine model (models/model.onnx, what Render serves) or, with rule=True, the rule-based v0."""
    if static_dir is None:
        monkeypatch.delenv("STATIC_DIR", raising=False)
    else:
        monkeypatch.setenv("STATIC_DIR", str(static_dir))
    for var in ("DATABASE_URL", "MODEL_PATH", *(() if keep_llm else ("LLM_API_KEY", "LLM_MODEL"))):
        monkeypatch.delenv(var, raising=False)
    if rule:
        monkeypatch.setenv("MODEL_PATH", "rule")
    from app.deps import reset_caches
    from app.main import create_app

    reset_caches()
    return TestClient(create_app())


@pytest.fixture()
def client(monkeypatch):
    """The API serving the real fields committed in static/fields (what Render serves)."""
    yield _make_client(monkeypatch)
    from app.deps import reset_caches

    reset_caches()


@pytest.fixture(scope="session")
def mock_static_dir(tmp_path_factory):
    """Demo fields with sources, catalogs and agent tours, built with the pipeline on synthetic exposures."""
    from pipeline.targets import load_targets
    from scripts.make_mock_static import build_target

    root = tmp_path_factory.mktemp("static")
    work = tmp_path_factory.mktemp("fits")
    targets = load_targets()
    for tid in ("wise0855", "rdra"):
        build_target(targets[tid], root / "fields", work)
    return root


@pytest.fixture()
def mock_client(mock_static_dir, monkeypatch):
    """The API over demo fields (rule-based v0: the synthetic catalogs carry no CatWISE photometry for the model)."""
    yield _make_client(monkeypatch, mock_static_dir, rule=True)
    from app.deps import reset_caches

    reset_caches()
