"""Classification engine as seen by the API: one interface, two implementations.

- RulePredictor (v0, today): methane index + motion, no training.
- OnnxPredictor: the trained model exported to ONNX by the model repo (Motor/), bundled in models/.

Contract with the model repo (what it must publish per version):
    model.onnx      input: float32 [1, n_features]; LAST output: class probabilities [1, n_classes]
    metadata.json   {"model_version", "features": [...], "classes": [...], "calibrated": bool,
                     "thresholds": {class: p}, "fill_values": {feature: value},
                     "scaler": {"mean": [...], "scale": [...]}  (optional, same order as features)}
The preprocessing done in training (missing values, scaling) MUST be repeated here
from metadata.json, otherwise training and serving see different inputs.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Protocol

import numpy as np

from app.domain.vocab import ReviewReason, SourceClass
from app.schemas import CLASSES
from app.services.features import COLOUR_PAIRS

SPHEREX_COLOURS = tuple(f"spx_{name}" for name, _, _ in COLOUR_PAIRS)

# BR-CLS-02: a catalog type is never a model input; a model that asks for one is refused at load.
FORBIDDEN_FEATURES = frozenset({"known_label", "simbad_type", "catalog_type", "catalog_status", "known_source"})


class Predictor(Protocol):
    method: str  # BR-CLS-01: every classification declares method and version
    version: str
    calibrated: bool  # BR-CLS-03
    thresholds: dict[str, float]
    rule_params: dict[str, float] | None

    def predict(self, evidence: dict) -> dict:  # -> {"label", "class_probs": {class: p}, "reasons": [...]}
        ...


def _pm_total(evidence: dict) -> float:
    pm = evidence.get("pm_mas_yr") or {}
    try:
        return math.hypot(float(pm.get("pmra", 0.0)), float(pm.get("pmdec", 0.0)))
    except (TypeError, ValueError):
        return 0.0


class RulePredictor:
    """Physical rule without training (thresholds are provisional; the final one is pending)."""

    method = "rule"
    calibrated = False
    thresholds: dict[str, float] = {}

    def __init__(
        self,
        methane_min: float = 3.2,
        motion_px_min: float = 1.0,
        pm_min_masyr: float = 100.0,
        version: str = "rule-v0",
    ):
        self.version = version
        self.rule_params = {
            "methane_index_min": methane_min,
            "motion_px_min": motion_px_min,
            "pm_min_mas_yr": pm_min_masyr,
        }
        self._methane_min, self._motion_min, self._pm_min = methane_min, motion_px_min, pm_min_masyr

    def predict(self, evidence: dict) -> dict:
        moving = (evidence.get("motion_px") or 0.0) >= self._motion_min or _pm_total(evidence) >= self._pm_min
        methane = evidence.get("methane_index")
        reasons: list[str] = []
        if evidence.get("jpl_match"):
            label = SourceClass.ASTEROID_COMET
        elif evidence.get("extended"):
            label = SourceClass.GALAXY
        elif methane is not None and methane >= self._methane_min:
            # BR-CLS-04: methane-like colour without motion can be a quasar or an artefact: send to review
            label = SourceClass.COLD_BROWN_DWARF if moving else SourceClass.UNKNOWN
            if not moving:
                reasons.append(ReviewReason.METHANE_WITHOUT_MOTION)
        elif methane is None and not evidence.get("in_gaia") and not moving:
            label = SourceClass.UNKNOWN
            reasons.append(ReviewReason.INSUFFICIENT_DATA)
        else:
            label = SourceClass.STAR
        return {
            "label": label.value,
            "class_probs": {c: 1.0 if c == label else 0.0 for c in CLASSES},
            "reasons": [r.value for r in reasons],
        }


class OnnxPredictor:
    """The engine model plus the rules it cannot learn.

    Before the model: a JPL match is an asteroid or comet and an extended source a galaxy (classes the model was not
    trained on). For a model that reads the CatWISE colour (the engine model), a source with neither `cw_W1_W2` nor
    MIN_SPHEREX_COLOURS SPHEREx colours is `unknown` with `insufficient_data`: otherwise the model would answer from
    its fill values alone.
    After the model: a cold-dwarf answer without motion becomes `unknown` with `methane_without_motion` (BR-CLS-04,
    same rule as RulePredictor): red colours without motion are also young stars, quasars and artefacts, which the
    model never saw.
    """

    method = "model"
    MIN_SPHEREX_COLOURS = 3

    def __init__(
        self,
        model_path: Path,
        metadata_path: Path | None = None,
        motion_px_min: float = 1.0,
        pm_min_masyr: float = 100.0,
    ):
        import onnxruntime as ort  # only imported when a model is configured

        metadata_path = metadata_path or Path(model_path).with_name("metadata.json")
        meta = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
        self.version = meta["model_version"]
        self.features: list[str] = meta["features"]
        forbidden = FORBIDDEN_FEATURES.intersection(self.features)
        if forbidden:
            raise ValueError(f"BR-CLS-02: catalog types cannot be model inputs: {sorted(forbidden)}")
        self.classes: list[str] = meta["classes"]
        unknown = set(self.classes) - set(CLASSES)
        if unknown:
            raise ValueError(f"model classes outside the API vocabulary: {sorted(unknown)}")
        self.calibrated = bool(meta.get("calibrated", False))
        self.thresholds = {k: float(v) for k, v in meta.get("thresholds", {}).items()}
        self._motion_min, self._pm_min = motion_px_min, pm_min_masyr
        self._evidence_rule = "cw_W1_W2" in self.features
        self.rule_params = {"motion_px_min": motion_px_min, "pm_min_mas_yr": pm_min_masyr}
        if self._evidence_rule:
            self.rule_params["min_spherex_colours"] = float(self.MIN_SPHEREX_COLOURS)
        self._fill = meta.get("fill_values", {})
        scaler = meta.get("scaler") or {}
        self._mean = np.asarray(scaler.get("mean", [0.0] * len(self.features)), dtype=np.float32)
        self._scale = np.asarray(scaler.get("scale", [1.0] * len(self.features)), dtype=np.float32)
        self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self._input = self._session.get_inputs()[0].name

    @staticmethod
    def _present(evidence: dict, name: str) -> bool:
        value = evidence.get(name)
        return value is not None and not (isinstance(value, float) and math.isnan(value))

    def _vector(self, evidence: dict) -> np.ndarray:
        flat = dict(evidence)
        pm = evidence.get("pm_mas_yr") or {}
        flat.setdefault("pm_total_mas_yr", _pm_total(evidence) if pm else None)
        row = []
        for name in self.features:
            value = flat.get(name)
            if isinstance(value, bool):
                value = float(value)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                value = self._fill.get(name, 0.0)
            row.append(float(value))
        x = (np.asarray(row, dtype=np.float32) - self._mean) / self._scale
        return x.reshape(1, -1)

    def _fixed(self, label: SourceClass, reasons: list[str]) -> dict:
        return {
            "label": label.value,
            "class_probs": {c: 1.0 if c == label else 0.0 for c in CLASSES},
            "reasons": reasons,
        }

    def predict(self, evidence: dict) -> dict:
        if evidence.get("jpl_match"):
            return self._fixed(SourceClass.ASTEROID_COMET, [])
        if evidence.get("extended"):
            return self._fixed(SourceClass.GALAXY, [])
        n_colours = sum(self._present(evidence, f) for f in SPHEREX_COLOURS)
        if self._evidence_rule and not self._present(evidence, "cw_W1_W2") and n_colours < self.MIN_SPHEREX_COLOURS:
            return self._fixed(SourceClass.UNKNOWN, [ReviewReason.INSUFFICIENT_DATA.value])
        probs = np.asarray(self._session.run(None, {self._input: self._vector(evidence)})[-1], dtype=float).ravel()
        class_probs = {c: float(p) for c, p in zip(self.classes, probs, strict=True)}
        best = max(class_probs, key=class_probs.get)
        threshold = self.thresholds.get(best, 0.0)
        label = best if class_probs[best] >= threshold else SourceClass.UNKNOWN.value
        reasons = [] if label == best else [ReviewReason.BELOW_THRESHOLD.value]
        if label == SourceClass.COLD_BROWN_DWARF:
            moving = (evidence.get("motion_px") or 0.0) >= self._motion_min or _pm_total(evidence) >= self._pm_min
            if not moving:
                label = SourceClass.UNKNOWN.value
                reasons.append(ReviewReason.METHANE_WITHOUT_MOTION.value)
        return {"label": label, "class_probs": {c: class_probs.get(c, 0.0) for c in CLASSES}, "reasons": reasons}


def load_predictor(model_path: Path | None) -> Predictor:
    if model_path and Path(model_path).is_file():
        return OnnxPredictor(Path(model_path))
    return RulePredictor()
