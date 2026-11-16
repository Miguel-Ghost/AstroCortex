"""The engine model bundled in models/ (published from Motor/) as /api/sources uses it."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from app.services.classifier import OnnxPredictor
from app.services.features import catwise_features, model_features, spherex_features

BACKEND = Path(__file__).resolve().parents[1]
BUNDLED = BACKEND / "models" / "model.onnx"
PROMOTED = BACKEND.parent / "Motor" / "artifacts" / "models" / "actual"


@pytest.fixture(scope="module")
def engine():
    return OnnxPredictor(BUNDLED)


def test_catwise_features_follow_the_training_formulas():
    out = catwise_features({"w1": 15.0, "w2": 13.0, "pmra": 300.0, "pmdec": 400.0})  # catalogs.json: mas/yr
    assert out["cw_W1_W2"] == pytest.approx(2.0)
    assert out["cw_mu"] == pytest.approx(0.5)
    assert out["Hrpm_W2"] == pytest.approx(13.0 + 5 * math.log10(0.5) + 5)
    still = catwise_features({"w1": 15.0, "w2": 13.0, "pmra": 0.0, "pmdec": 0.0})
    assert still["Hrpm_W2"] == pytest.approx(13.0 + 5 * math.log10(0.005) + 5)  # motion floor


def test_catwise_artefact_flags_drop_the_band():
    out = catwise_features({"w1": 15.0, "w2": 13.0, "pmra": 0.0, "pmdec": 0.0, "cc_flags": "0d00", "ab_flags": "00"})
    assert "cw_W1_W2" not in out and "Hrpm_W2" not in out and "cw_mu" in out


def test_spherex_colours_need_snr_3_in_both_detectors():
    phot = {
        "D1": {"flux": 1.0, "flux_err": 0.1, "snr": 10.0},
        "D2": {"flux": 2.0, "flux_err": 0.1, "snr": 20.0},
        "D3": {"flux": 2.0, "flux_err": 1.0, "snr": 2.0},
        "D4": {"flux": 0.01, "flux_err": 0.1, "snr": 0.1},
        "D5": {"flux": 3.0, "flux_err": 0.3, "snr": 10.0},
    }
    out = spherex_features(phot)
    assert out["spx_c21"] == pytest.approx(-2.5 * math.log10(2.0))
    assert "spx_c32" not in out and "spx_c54" not in out  # D3 and D4 below S/N 3
    assert out["spx_ch4"] == pytest.approx(math.log10(3.0 / 0.3))  # D4 undetected: lower limit with 3 sigma


def test_bundled_model_is_the_promoted_one():
    meta = json.loads((BACKEND / "models" / "metadata.json").read_text(encoding="utf-8"))
    assert meta["classes"] == ["star", "cold_brown_dwarf"] and "cw_W1_W2" in meta["features"]
    if not (PROMOTED / "model.onnx").is_file():
        pytest.skip("Motor/ not present")
    promoted = json.loads((PROMOTED / "metadata.json").read_text(encoding="utf-8"))
    assert meta["model_version"] == promoted["model_version"]
    digest = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (BUNDLED, PROMOTED / "model.onnx")]
    assert digest[0] == digest[1], "publish again: python Motor/main.py publicar"


def test_rules_around_the_model(engine):
    cold = {"cw_W1_W2": 3.0, "cw_mu": 2.0, "Hrpm_W2": 21.0, "spx_ch4": 1.0}
    assert engine.predict({**cold, "pm_mas_yr": {"pmra": 2000.0, "pmdec": 0.0}})["label"] == "cold_brown_dwarf"
    still = engine.predict(cold)  # red colours, no motion: young star, quasar or artefact as much as a dwarf
    assert still["label"] == "unknown" and still["reasons"] == ["methane_without_motion"]
    empty = engine.predict({"in_gaia": True})
    assert empty["label"] == "unknown" and empty["reasons"] == ["insufficient_data"]
    assert engine.predict({**cold, "jpl_match": "2001 AB"})["label"] == "asteroid_comet"


@pytest.mark.parametrize(
    ("field", "label"),
    [
        ("wise0855", "cold_brown_dwarf"),
        ("epsindib", "cold_brown_dwarf"),
        ("barnard", "star"),
        ("rwaur", "star"),
        ("rdra", "unknown"),  # saturated, no CatWISE counterpart, one SPHEREx colour: insufficient data
    ],
)
def test_targets_of_the_real_fields(client, field, label):
    body = client.get("/api/sources", params={"field_id": field}).json()
    assert body["method"] == "model"
    target = next(s for s in body["sources"] if s["is_target"])
    assert target["label"] == label
    if label == "unknown":
        assert "insufficient_data" in target["review_reasons"]
    else:
        assert target["review_status"] == "known"


def test_response_evidence_carries_the_model_inputs(client):
    body = client.get("/api/sources", params={"field_id": "wise0855"}).json()
    target = next(s for s in body["sources"] if s["is_target"])
    raw = json.loads((BACKEND / "static" / "fields" / "wise0855" / "sources.json").read_text(encoding="utf-8"))
    catalogs = json.loads((BACKEND / "static" / "fields" / "wise0855" / "catalogs.json").read_text(encoding="utf-8"))
    from app.services.features import wise_index

    expected = model_features(next(r for r in raw["sources"] if r["is_target"]), wise_index(catalogs))
    assert expected["cw_W1_W2"] > 2.0  # WISE 0855: W1 - W2 ~ 2.8
    for key, value in expected.items():
        assert target["evidence"][key] == pytest.approx(value)
