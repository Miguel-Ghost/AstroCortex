"""Classification engine as seen by the API: one interface, two implementations.

- RulePredictor (v0, today): methane index + motion, no training.
- OnnxPredictor (Sunday): the trained model exported to ONNX by the model repo.

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

from app.schemas import CLASSES


class Predictor(Protocol):
    method: str
    version: str
    calibrated: bool
    thresholds: dict[str, float]
    rule_params: dict[str, float] | None

    def predict(self, evidence: dict) -> dict:  # -> {"label": str, "class_probs": {class: p}}
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

    def __init__(self, methane_min: float = 3.2, motion_px_min: float = 1.0, pm_min_masyr: float = 100.0,
                 version: str = "rule-v0"):
        self.version = version
        self.rule_params = {"methane_index_min": methane_min, "motion_px_min": motion_px_min,
                            "pm_min_mas_yr": pm_min_masyr}
        self._methane_min, self._motion_min, self._pm_min = methane_min, motion_px_min, pm_min_masyr

    def predict(self, evidence: dict) -> dict:
        moving = (evidence.get("motion_px") or 0.0) >= self._motion_min or _pm_total(evidence) >= self._pm_min
        methane = evidence.get("methane_index")
        if evidence.get("jpl_match"):
            label = "asteroid_comet"
        elif evidence.get("extended"):
            label = "galaxy"
        elif methane is not None and methane >= self._methane_min:
            # methane-like colour without motion can be a quasar or an artefact: send to review
            label = "cold_brown_dwarf" if moving else "unknown"
        elif methane is None and not evidence.get("in_gaia") and not moving:
            label = "unknown"
        else:
            label = "star"
        return {"label": label, "class_probs": {c: 1.0 if c == label else 0.0 for c in CLASSES}}


class OnnxPredictor:
    method = "model"

    def __init__(self, model_path: Path, metadata_path: Path | None = None):
        import onnxruntime as ort  # only imported when a model is configured

        metadata_path = metadata_path or Path(model_path).with_name("metadata.json")
        meta = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
        self.version = meta["model_version"]
        self.features: list[str] = meta["features"]
        self.classes: list[str] = meta["classes"]
        self.calibrated = bool(meta.get("calibrated", False))
        self.thresholds = {k: float(v) for k, v in meta.get("thresholds", {}).items()}
        self.rule_params = None
        self._fill = meta.get("fill_values", {})
        scaler = meta.get("scaler") or {}
        self._mean = np.asarray(scaler.get("mean", [0.0] * len(self.features)), dtype=np.float32)
        self._scale = np.asarray(scaler.get("scale", [1.0] * len(self.features)), dtype=np.float32)
        self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self._input = self._session.get_inputs()[0].name

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

    def predict(self, evidence: dict) -> dict:
        probs = np.asarray(self._session.run(None, {self._input: self._vector(evidence)})[-1], dtype=float).ravel()
        class_probs = {c: float(p) for c, p in zip(self.classes, probs)}
        best = max(class_probs, key=class_probs.get)
        threshold = self.thresholds.get(best, 0.0)
        label = best if class_probs[best] >= threshold else "unknown"
        return {"label": label, "class_probs": {c: class_probs.get(c, 0.0) for c in CLASSES}}


def load_predictor(model_path: Path | None) -> Predictor:
    if model_path and Path(model_path).is_file():
        return OnnxPredictor(Path(model_path))
    return RulePredictor()


PRIORITY = {"cold_brown_dwarf": 0, "unknown": 1, "asteroid_comet": 2, "galaxy": 3, "star": 4}


def sort_candidates_first(sources: list[dict]) -> list[dict]:
    """Cold brown dwarfs first, then unknowns that move, then the rest."""
    def key(s: dict) -> tuple:
        moving = (s["evidence"].get("motion_px") or 0) >= 1 or _pm_total(s["evidence"]) >= 100
        p = PRIORITY.get(s["label"], 9) + (0 if s["label"] != "unknown" or moving else 0.5)
        return (p, -s["class_probs"].get(s["label"], 0.0))
    return sorted(sources, key=key)
