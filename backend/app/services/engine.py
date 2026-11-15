"""Classifies the sources of a field: prediction + review status. Shared by /api/sources and the agent."""

from __future__ import annotations

from app.config import Settings
from app.schemas import CLASSES
from app.services.classifier import Predictor
from app.services.review import assess, sort_for_review, summarize
from app.services.static_store import StaticStore


def classify_field(field_id: str, store: StaticStore, predictor: Predictor, settings: Settings) -> dict | None:
    ref = store.resolve(field_id)
    if ref is None:
        return None
    raw = store.read_json(field_id, "sources.json")
    if raw is None:
        raw = target_only(store, ref)  # BR-CLS-06
        if raw is None:
            return None
    field_id = ref.field_id  # canonical id in every response (BR-FIELD-06)
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
        "catalogs_checked": raw.get("catalogs_checked") if isinstance(raw, dict) else None,
        "methane_index_definition": raw.get("methane_index_definition") if isinstance(raw, dict) else None,
        "summary": summarize(sources),
        "sources": sources,
    }


def target_only(store: StaticStore, ref) -> dict | None:
    """Sources of a published field whose measured list is missing: its target, from the manifest
    and the target catalog (BR-CLS-06). Nothing is measured, so nothing is invented: the evidence
    carries only the catalog motion and the dates the target was imaged."""
    target = store.targets.get(ref.target_id or "")
    manifest = store.manifest(ref.field_id)
    if target is None or manifest is None:
        return None
    epochs = manifest.get("epochs", [])
    positions = {
        e["epoch_id"]: {k: e["expected_position"][k] for k in ("x", "y", "ra", "dec")}
        for e in epochs
        if e.get("expected_position")
    }
    mid = (
        epochs[len(epochs) // 2]["expected_position"]
        if epochs and epochs[len(epochs) // 2].get("expected_position")
        else None
    )
    if mid is None:
        return None
    known = target.kind if target.kind in CLASSES else "star"
    return {
        "field_id": ref.field_id,
        "synthetic": False,
        "catalogs_checked": False,
        "sources": [
            {
                "source_id": f"{target.target_id}_s00",
                "name": target.name,
                "is_target": True,
                "ra": mid["ra"],
                "dec": mid["dec"],
                "x": mid["x"],
                "y": mid["y"],
                "positions": positions,
                "epoch_mjd": manifest.get("center_ref_mjd"),
                "evidence": {
                    "pm_mas_yr": {"pmra": target.pmra_masyr, "pmdec": target.pmdec_masyr},
                    "n_epochs_detected": len(positions),
                },
                "catalog": {
                    "status": "known_typed",
                    "known_label": known,
                    "known_source": "SIMBAD",
                    "simbad_type": target.kind,
                },
            }
        ],
    }
