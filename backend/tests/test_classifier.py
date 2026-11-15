from __future__ import annotations

import json

import numpy as np
import pytest

from app.services.classifier import OnnxPredictor, RulePredictor

RULE = RulePredictor()


@pytest.mark.parametrize(
    "evidence, label",
    [
        ({"methane_index": 40, "pm_mas_yr": {"pmra": -8124, "pmdec": 673}, "in_gaia": False}, "cold_brown_dwarf"),
        ({"methane_index": 40, "motion_px": 0.0, "in_gaia": False}, "unknown"),  # methane-like but static
        ({"jpl_match": "2001 AB", "methane_index": 1.0}, "asteroid_comet"),
        ({"extended": True, "methane_index": 1.0}, "galaxy"),
        ({"methane_index": 1.0, "in_gaia": True, "pm_mas_yr": {"pmra": -801, "pmdec": 10362}}, "star"),
        ({"in_gaia": False}, "unknown"),  # no data at all
    ],
)
def test_rule_predictor(evidence, label):
    """BR-CLS-04 (methane without motion -> review) and BR-CLS-01 (method declared)."""
    assert RULE.method == "rule" and RULE.version
    out = RULE.predict(evidence)
    assert out["label"] == label
    if label == "unknown":
        assert out["reasons"]  # an unknown always says why
    assert out["class_probs"][label] == 1.0


@pytest.fixture()
def tiny_model(tmp_path):
    """A 2-feature softmax 'model' exported to ONNX, with the metadata the model repo must publish."""
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper, numpy_helper

    classes = ["star", "galaxy", "asteroid_comet", "cold_brown_dwarf", "unknown"]
    w = np.zeros((2, 5), dtype=np.float32)
    w[0, 3] = 2.0  # methane_index pushes towards cold_brown_dwarf
    w[1, 0] = 2.0  # in_gaia pushes towards star
    graph = helper.make_graph(
        [
            helper.make_node("MatMul", ["x", "W"], ["logits"]),
            helper.make_node("Softmax", ["logits"], ["probs"], axis=1),
        ],
        "tiny",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 2])],
        [helper.make_tensor_value_info("probs", TensorProto.FLOAT, [1, 5])],
        [numpy_helper.from_array(w, name="W")],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.save(model, tmp_path / "model.onnx")
    (tmp_path / "metadata.json").write_text(
        json.dumps(
            {
                "model_version": "tiny-0.1",
                "features": ["methane_index", "in_gaia"],
                "classes": classes,
                "calibrated": True,
                "thresholds": {"cold_brown_dwarf": 0.7},
                "fill_values": {"methane_index": 1.0},
                "scaler": {"mean": [0.0, 0.0], "scale": [1.0, 1.0]},
            }
        )
    )
    return tmp_path / "model.onnx"


def test_onnx_predictor_follows_the_contract(tiny_model):
    predictor = OnnxPredictor(tiny_model)
    assert predictor.method == "model" and predictor.version == "tiny-0.1"
    dwarf = predictor.predict({"methane_index": 5.0, "in_gaia": False})
    assert dwarf["label"] == "cold_brown_dwarf"
    assert sum(dwarf["class_probs"].values()) == pytest.approx(1.0, abs=1e-5)
    weak = predictor.predict({"methane_index": None, "in_gaia": False})  # filled with 1.0 -> p = 0.65 < 0.7
    assert weak["label"] == "unknown" and weak["reasons"] == ["low_confidence"]


def test_model_cannot_use_catalog_types_as_input(tiny_model):
    """BR-CLS-02."""
    meta_path = tiny_model.with_name("metadata.json")
    meta = json.loads(meta_path.read_text())
    meta["features"] = ["methane_index", "known_label"]
    meta_path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="BR-CLS-02"):
        OnnxPredictor(tiny_model)


def test_rule_scores_are_flagged_uncalibrated():
    """BR-CLS-03."""
    assert RULE.calibrated is False
