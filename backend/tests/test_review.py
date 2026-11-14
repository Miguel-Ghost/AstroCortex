"""BR-CLS-05: review status, catalog agreement, reasons, order and summary."""

from __future__ import annotations

from app.services.classifier import RulePredictor
from app.services.review import assess, sort_for_review, summarize

RULE = RulePredictor()


def review(row: dict) -> dict:
    prediction = RULE.predict(row["evidence"])
    return {**row, **prediction, **assess(row, prediction)}


KNOWN_DWARF = {
    "source_id": "wise0855",
    "evidence": {"methane_index": 40, "pm_mas_yr": {"pmra": -8124, "pmdec": 673}, "motion_px": 1.3, "in_gaia": False},
    "catalog": {"status": "known_typed", "known_label": "cold_brown_dwarf", "known_source": "SIMBAD"},
}
GAIA_STAR = {
    "source_id": "star",
    "evidence": {"methane_index": 1.0, "pm_mas_yr": {"pmra": 3, "pmdec": -2}, "motion_px": 0.0, "in_gaia": True},
    "catalog": {"status": "catalogued_untyped", "gaia_id": "123"},
}
RED_STATIC = {
    "source_id": "red",
    "evidence": {"methane_index": 6.0, "motion_px": 0.0, "in_gaia": False, "in_catwise": False},
}
NEW_DWARF = {
    "source_id": "new",
    "evidence": {"methane_index": 9.0, "pm_mas_yr": {"pmra": 900, "pmdec": 0}, "in_gaia": False, "in_catwise": True},
}
WRONG_TYPE = {
    "source_id": "disagree",
    "evidence": {"methane_index": 1.0, "in_gaia": True},
    "catalog": {"status": "known_typed", "known_label": "galaxy", "known_source": "SIMBAD"},
}
FAST_UNCATALOGUED_MOTION = {
    "source_id": "mover",
    "evidence": {"methane_index": 1.0, "motion_px": 2.1, "pm_mas_yr": {"pmra": 1, "pmdec": 1}, "in_gaia": True},
}


def test_known_source_that_agrees_is_known():
    r = review(KNOWN_DWARF)
    assert (r["agreement"], r["review_status"]) == ("agrees", "known")
    assert r["review_reasons"] == ["no_gaia_counterpart"]  # informative only


def test_catalogued_untyped_star_is_classified():
    r = review(GAIA_STAR)
    assert (r["label"], r["agreement"], r["review_status"]) == ("star", "no_reference", "classified")


def test_methane_without_motion_and_no_counterpart_needs_review():
    r = review(RED_STATIC)
    assert r["label"] == "unknown" and r["review_status"] == "needs_review"
    assert r["catalog"]["status"] == "uncatalogued"  # inferred: no counterpart in the evidence
    assert r["review_reasons"][:2] == ["methane_without_motion", "uncatalogued"]


def test_cold_dwarf_not_in_known_lists_is_a_candidate_to_review():
    r = review(NEW_DWARF)
    assert r["label"] == "cold_brown_dwarf" and r["review_status"] == "needs_review"
    assert "methane_index_high_not_known" in r["review_reasons"]


def test_disagreement_with_catalog_needs_review():
    r = review(WRONG_TYPE)
    assert (r["agreement"], r["review_status"]) == ("disagrees", "needs_review")
    assert "disagrees_with_catalog" in r["review_reasons"]


def test_motion_without_catalog_motion_needs_review():
    r = review(FAST_UNCATALOGUED_MOTION)
    assert r["review_status"] == "needs_review" and "moves_without_catalog_motion" in r["review_reasons"]


def test_single_epoch_and_flagged_sources_need_review():
    one_epoch = {"source_id": "a", "evidence": {"methane_index": 1.0, "in_gaia": True, "n_epochs_detected": 1}}
    flagged = {"source_id": "b", "evidence": {"methane_index": 1.0, "in_gaia": True, "flagged_frac": 0.8}}
    assert review(one_epoch)["review_reasons"] == ["only_in_one_epoch"]
    assert review(flagged)["review_reasons"] == ["high_flagged_fraction"]


def test_order_and_summary():
    rows = [review(r) for r in (KNOWN_DWARF, GAIA_STAR, RED_STATIC, NEW_DWARF)]
    ordered = [r["source_id"] for r in sort_for_review(rows)]
    assert ordered[:2] in (["red", "new"], ["new", "red"]) and ordered[2:] == ["star", "wise0855"]
    assert summarize(rows) == {"n_sources": 4, "needs_review": 2, "classified": 1, "known": 1}
