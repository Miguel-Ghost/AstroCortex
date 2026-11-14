"""Classifies the sources of a field: prediction + review status. Shared by /api/sources and the agent."""

from __future__ import annotations

from app.config import Settings
from app.schemas import CLASSES
from app.services.classifier import Predictor
from app.services.review import assess, sort_for_review, summarize
from app.services.static_store import StaticStore


def classify_field(field_id: str, store: StaticStore, predictor: Predictor, settings: Settings) -> dict | None:
    raw = store.read_json(field_id, "sources.json")
    if raw is None:
        return None
    rows = raw["sources"] if isinstance(raw, dict) else raw
    sources = []
    for row in rows:
        prediction = predictor.predict(row.get("evidence") or {})
        review = assess(row, prediction)
        sources.append({**row, "label": prediction["label"], "class_probs": prediction["class_probs"], **review})
    sources = sort_for_review(sources)
    manifest = store.manifest(field_id) or {}
    return {
        "field_id": field_id,
        "method": predictor.method,  # BR-CLS-01
        "model_version": predictor.version,
        "pipeline_commit": manifest.get("pipeline_commit", settings.commit),
        "data_release": manifest.get("data_release", settings.data_release),
        "synthetic": bool(isinstance(raw, dict) and raw.get("synthetic")),  # BR-FIELD-03
        "calibrated": predictor.calibrated,  # BR-CLS-03
        "classes": list(CLASSES),
        "thresholds": predictor.thresholds,
        "rule_params": predictor.rule_params,
        "summary": summarize(sources),
        "sources": sources,
    }
