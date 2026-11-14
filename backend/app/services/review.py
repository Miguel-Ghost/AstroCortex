"""Review status of each classified source (BR-CLS-05).

A source is `known` when a catalog already types it and the engine agrees, `needs_review` when
something about it needs a human look, and `classified` otherwise. `needs_review` is a candidate
to inspect, never a discovery.
"""

from __future__ import annotations

import math

from app.domain.vocab import Agreement, CatalogStatus, ReviewReason, ReviewStatus, SourceClass

MOTION_PX_MIN = 1.0  # displacement within SPHEREx data that counts as moving
CATALOG_PM_MIN = 100.0  # mas/yr; below this the catalog does not explain a visible motion
FLAGGED_FRACTION_MAX = 0.5
ORDER = {ReviewStatus.NEEDS_REVIEW: 0, ReviewStatus.CLASSIFIED: 1, ReviewStatus.KNOWN: 2}


def _pm_total(evidence: dict) -> float:
    pm = evidence.get("pm_mas_yr") or {}
    try:
        return math.hypot(float(pm.get("pmra") or 0.0), float(pm.get("pmdec") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def catalog_info(row: dict) -> dict:
    """The row's catalog block; if the cross-match did not send one, infer the status from the evidence."""
    catalog = dict(row.get("catalog") or {})
    if not catalog.get("status"):
        evidence = row.get("evidence") or {}
        in_any = bool(evidence.get("in_gaia") or evidence.get("in_catwise") or evidence.get("jpl_match"))
        catalog["status"] = (CatalogStatus.CATALOGUED_UNTYPED if in_any else CatalogStatus.UNCATALOGUED).value
    return catalog


def assess(row: dict, prediction: dict) -> dict:
    """agreement, review_status and review_reasons for one source (BR-CLS-05)."""
    evidence = row.get("evidence") or {}
    catalog = catalog_info(row)
    label = prediction["label"]
    reasons: list[str] = list(prediction.get("reasons", []))

    known = catalog.get("known_label")
    if catalog["status"] == CatalogStatus.KNOWN_TYPED and known:
        agreement = Agreement.AGREES if known == label else Agreement.DISAGREES
    else:
        agreement = Agreement.NO_REFERENCE

    if agreement == Agreement.DISAGREES:
        reasons.append(ReviewReason.DISAGREES_WITH_CATALOG)
    if label == SourceClass.UNKNOWN and not reasons:
        reasons.append(ReviewReason.BELOW_THRESHOLD)
    if (evidence.get("motion_px") or 0.0) >= MOTION_PX_MIN and _pm_total(evidence) < CATALOG_PM_MIN:
        reasons.append(ReviewReason.MOVES_WITHOUT_CATALOG_MOTION)
    if label == SourceClass.COLD_BROWN_DWARF and catalog["status"] != CatalogStatus.KNOWN_TYPED:
        reasons.append(ReviewReason.METHANE_INDEX_HIGH_NOT_KNOWN)
    if evidence.get("n_epochs_detected") == 1:
        reasons.append(ReviewReason.ONLY_IN_ONE_EPOCH)
    if catalog["status"] == CatalogStatus.UNCATALOGUED:
        reasons.append(ReviewReason.UNCATALOGUED)
    if (evidence.get("flagged_frac") or 0.0) > FLAGGED_FRACTION_MAX:
        reasons.append(ReviewReason.HIGH_FLAGGED_FRACTION)
    if evidence.get("in_gaia") is False:
        reasons.append(ReviewReason.NO_GAIA_COUNTERPART)  # informative only

    reasons = list(dict.fromkeys(str(r) for r in reasons))  # de-duplicate, keep order
    triggers = [r for r in reasons if r != ReviewReason.NO_GAIA_COUNTERPART]
    if triggers:
        status = ReviewStatus.NEEDS_REVIEW
    elif agreement == Agreement.AGREES:
        status = ReviewStatus.KNOWN
    else:
        status = ReviewStatus.CLASSIFIED
    return {
        "catalog": catalog,
        "agreement": agreement.value,
        "review_status": status.value,
        "review_reasons": reasons,
    }


def sort_for_review(sources: list[dict]) -> list[dict]:
    """needs_review first (more reasons first), then classified, then known (BR-CLS-05)."""

    def key(s: dict) -> tuple:
        triggers = [r for r in s["review_reasons"] if r != ReviewReason.NO_GAIA_COUNTERPART]
        return (ORDER[ReviewStatus(s["review_status"])], -len(triggers), -s["class_probs"].get(s["label"], 0.0))

    return sorted(sources, key=key)


def summarize(sources: list[dict]) -> dict:
    counts = {s.value: 0 for s in ReviewStatus}
    for s in sources:
        counts[s["review_status"]] += 1
    return {"n_sources": len(sources), **counts}
