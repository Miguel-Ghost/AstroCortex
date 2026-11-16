"""Model inputs computed from a source row and the field's catalogs.json, with the training formulas.

The engine model (Motor/, artifacts/models/actual/metadata.json -> feature_definitions) was trained on:

    cw_W1_W2   CatWISE2020 w1mpro - w2mpro [Vega mag]; missing when the cc_flags/ab_flags of W1 or W2 are not "0"
    cw_mu      hypot(pmra, pmdec) from CatWISE2020 [arcsec/yr]
    Hrpm_W2    w2mpro + 5 log10(max(cw_mu, 0.005)) + 5 [mag], reduced proper motion
    spx_cAB    -2.5 log10(F_DA / F_DB) for the detector pairs 21, 32, 43, 54, 65 and 64; only with S/N >= 3 in both
    spx_ch4    log10(F_D5 / F_D4) = log10(methane_index); D5 S/N >= 3 and D4 S/N < 3 -> log10(F_D5 / (3 sigma_D4))

Here the SPHEREx fluxes are the forced PSF photometry of the row (`photometry`, per detector, on the coadds) and the
CatWISE values come from the catalogs.json row whose name is the source's `catalog.catwise_id`. Missing inputs stay
missing: the predictor fills them with the training medians (metadata `fill_values`).
"""

from __future__ import annotations

import math

SNR_COLOUR_MIN = 3.0
MU_FLOOR_ARCSEC_YR = 0.005
COLOUR_PAIRS = (("c21", 2, 1), ("c32", 3, 2), ("c43", 4, 3), ("c54", 5, 4), ("c65", 6, 5), ("c64", 6, 4))
SPHEREX_FEATURES = tuple(f"spx_{name}" for name, _, _ in COLOUR_PAIRS) + ("spx_ch4",)
CATWISE_FEATURES = ("cw_W1_W2", "cw_mu", "Hrpm_W2")


def wise_index(catalogs: dict | None) -> dict[str, dict]:
    """catalogs.json CatWISE rows by name (the key that sources.json keeps in catalog.catwise_id)."""
    return {w["name"]: w for w in (catalogs or {}).get("wise", []) if w.get("name")}


def _num(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _clean_band(w: dict, band: int) -> bool:
    """False when CatWISE flags the band as an artefact (flags only present in catalogs fetched with them)."""
    for key in ("cc_flags", "ab_flags"):
        flags = w.get(key)
        if isinstance(flags, str) and len(flags) > band and flags[band] != "0":
            return False
    return True


def catwise_features(w: dict | None) -> dict[str, float]:
    if not w:
        return {}
    out: dict[str, float] = {}
    w1 = _num(w.get("w1")) if _clean_band(w, 0) else None
    w2 = _num(w.get("w2")) if _clean_band(w, 1) else None
    if w1 is not None and w2 is not None:
        out["cw_W1_W2"] = w1 - w2
    pmra, pmdec = _num(w.get("pmra")), _num(w.get("pmdec"))  # catalogs.json keeps CatWISE motion in mas/yr
    if pmra is not None and pmdec is not None:
        mu = math.hypot(pmra, pmdec) / 1000.0
        out["cw_mu"] = mu
        if w2 is not None:
            out["Hrpm_W2"] = w2 + 5.0 * math.log10(max(mu, MU_FLOOR_ARCSEC_YR)) + 5.0
    return out


def spherex_features(photometry: dict | None) -> dict[str, float]:
    phot = photometry or {}

    def det(d: int) -> tuple[float | None, float | None, float | None]:
        p = phot.get(f"D{d}") or {}
        return _num(p.get("flux")), _num(p.get("flux_err")), _num(p.get("snr"))

    out: dict[str, float] = {}
    for name, a, b in COLOUR_PAIRS:
        fa, _, sa = det(a)
        fb, _, sb = det(b)
        if None in (fa, fb, sa, sb):
            continue
        if sa >= SNR_COLOUR_MIN and sb >= SNR_COLOUR_MIN and fa > 0 and fb > 0:
            out[f"spx_{name}"] = -2.5 * math.log10(fa / fb)
    f5, _, s5 = det(5)
    f4, e4, s4 = det(4)
    if f5 is not None and s5 is not None and s5 >= SNR_COLOUR_MIN and f5 > 0:
        if s4 is not None and s4 >= SNR_COLOUR_MIN and f4 is not None and f4 > 0:
            out["spx_ch4"] = math.log10(f5 / f4)
        elif e4 is not None and e4 > 0:
            out["spx_ch4"] = math.log10(f5 / (3.0 * e4))
    return out


def model_features(row: dict, wise_by_name: dict[str, dict]) -> dict[str, float]:
    """The engine model's inputs for one source row (rounded like the rest of the evidence)."""
    catwise_id = (row.get("catalog") or {}).get("catwise_id")
    feats = {**catwise_features(wise_by_name.get(catwise_id)), **spherex_features(row.get("photometry"))}
    return {k: round(v, 4) for k, v in feats.items()}
