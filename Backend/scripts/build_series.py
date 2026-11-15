"""spectrum.json and lightcurve.json of every published target, measured on real SPHEREx data.

    python -m scripts.build_series --exposures <folder with <target>/manifest.json and frames/>

The exposures folder is the per-exposure output of the image pipeline (each SPHEREx DR1 exposure
cut out, ZODI subtracted and placed on the field's 31x31 grid, with its wavelength at the target).

- Spectrum: aperture photometry of the target in every single exposure. SPHEREx's linear variable
  filters give each exposure its own wavelength at the target's position, so the exposures together
  sample 0.75-5 um. The exposures were resampled onto the field grid (a point source moves by up to
  half a pixel), so an aperture of 1.5 px is used instead of a fixed-position PSF fit. Background
  from a 4-7 px annulus; neighbours from sources.json inside the aperture are subtracted with their
  coadd fluxes interpolated to the exposure's wavelength. An exposure that disagrees with the
  exposures at nearby wavelengths by more than 5 robust sigma (cosmic ray, glitch) is rejected.
- Light curve: each date samples different wavelengths, so absolute fluxes of different dates are not
  comparable. Every exposure is divided by the target's median flux at the same wavelength (all
  dates), and the ratios of each date are averaged: 1.0 is the mean brightness.
- Fluxes in mJy: the PSF-integrated surface brightness (MJy/sr summed over pixels) times the pixel
  solid angle. Errors add a 5 % systematic floor (PSF model, calibration), as in sources.json.
  Exposures whose target core pixel is masked (saturated or no data) go to `excluded`.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.services.static_store import StaticStore
from pipeline.sources import (
    FLUX_FLOOR,
    PSF_SIGMA_DEFAULT,
    FieldMeasurer,
    Frame,
    clipped_stats,
    forced_fluxes,
    psf_image,
)

ARCSEC_PER_RAD = 206264.806
DETECT_SNR = 3.0
MAX_CORE_MASKED = 0.5  # more than half of the 3x3 core masked: the flux is not usable
OUTLIER_WINDOW_UM = 0.08  # exposures within this distance in wavelength are compared
OUTLIER_NSIG = 5.0
OUTLIER_MIN_NEIGHBOURS = 4
LC_MIN_SNR = 5.0  # exposures used for the light curve
LC_WINDOW_UM = 0.05  # wavelength window of the reference spectrum
LC_MIN_NEIGHBOURS = 3
LC_MIN_PER_DATE = 3
LC_MAX_DET_CHI2 = 4.0  # reduced chi2 of the detectors around a date's value
PSF_FIT_BOUNDS = (0.2, 2.0)  # bounds of the width in FieldMeasurer.fit_psf_sigmas
AP_RADIUS_PX = 1.5  # aperture radius for single exposures (9.3 arcsec)
AN_INNER_PX, AN_OUTER_PX = 4.0, 7.0  # local background annulus
AP_MIN_VALID = 0.7  # fraction of the target's PSF flux that must fall on valid aperture pixels
GENERATED_BY = "scripts.build_series (photometry of the target on SPHEREx DR1 exposures and coadds)"
# WISE zero points (Vega), Jy, for the printed sanity check against CatWISE
WISE_ZERO_JY = {"w1": (3.35, 309.54), "w2": (4.60, 171.787)}


def mjy_per_unit(manifest: dict) -> float:
    """mJy per (MJy/sr x pixel)."""
    omega = (float(manifest["pixscale_arcsec"]) / ARCSEC_PER_RAD) ** 2
    return omega * 1e9


def core_state(data: np.ndarray, x: float, y: float) -> str | None:
    """None if the target's core can be measured, else the reason it cannot."""
    ny, nx = data.shape
    ix, iy = int(round(x)), int(round(y))
    if not (0 <= ix < nx and 0 <= iy < ny):
        return "outside the grid"
    if np.isnan(data[iy, ix]):
        return "core pixel masked (saturated or no data)"
    win = data[max(0, iy - 1) : iy + 2, max(0, ix - 1) : ix + 2]
    if np.isnan(win).mean() > MAX_CORE_MASKED:
        return "most of the core masked"
    return None


class ExposureSet(FieldMeasurer):
    """The single exposures of one field, loaded like coadds (for the PSF fit of FieldMeasurer)."""

    def __init__(self, exp_dir: Path, manifest: dict):  # noqa: D107 - FieldMeasurer.__init__ reads coadds
        self.manifest = json.loads((exp_dir / "manifest.json").read_text(encoding="utf-8"))
        self.grid = type("G", (), {"nx": manifest["nx"], "ny": manifest["ny"]})
        self.frames = []
        self.meta = []
        for e in self.manifest["epochs"]:
            for f in e["frames"]:
                path = exp_dir / "frames" / Path(f["data_url"]).name
                raw = np.fromfile(path, dtype="<f4").reshape(manifest["ny"], manifest["nx"]).astype(float)
                mu, sd = clipped_stats(raw)
                self.frames.append(Frame(0, int(f["detector"]), raw - mu, sd))
                self.meta.append((e["epoch_id"], f))
        self.detectors = sorted({fr.detector for fr in self.frames})


def exposure_psf_sigmas(sets: list[ExposureSet], fallback: dict[int, float]) -> dict[int, float]:
    """Median Gaussian width per detector of bright isolated stars in the single exposures.

    Single exposures are sharper than the coadds (no registration blur); fits that end on the
    bounds of the fit (undersampled cores, hot pixels) are left out."""
    widths: dict[int, list[float]] = {d: [] for d in range(1, 7)}
    for s in sets:
        for d, values in s.fit_psf_sigmas().items():
            widths[d] += [v for v in values if PSF_FIT_BOUNDS[0] + 0.01 < v < PSF_FIT_BOUNDS[1] - 0.01]
    return {d: (float(np.median(v)) if len(v) >= 10 else fallback[d]) for d, v in widths.items()}


def neighbour_flux(row: dict, wavelength: float | None, detector: int, centres: dict[int, float]) -> float | None:
    """Coadd flux of a neighbour at this wavelength (MJy/sr x pixel), if it was measured.

    A detector spans a wide band, so the six coadd fluxes are interpolated linearly in wavelength
    between the detector centres (constant beyond the first and last); a neighbour with a steep
    spectrum is then not over- or under-subtracted at the ends of a band."""
    phot = row.get("photometry") or {}
    pts = []
    for d, lam in sorted(centres.items(), key=lambda kv: kv[1]):
        f = (phot.get(f"D{d}") or {}).get("flux")
        if f is not None and math.isfinite(float(f)):
            pts.append((lam, float(f)))
    if not pts:
        return None
    if wavelength is None:
        own = (phot.get(f"D{detector}") or {}).get("flux")
        return float(own) if own is not None and math.isfinite(float(own)) else None
    lams, fluxes = zip(*pts, strict=True)
    return float(np.interp(wavelength, lams, fluxes))


def measure(
    frame: Frame,
    rows: list[dict],
    epoch_id: str,
    ti: int,
    sigma: float,
    k_mjy: float,
    wavelength: float | None = None,
    centres: dict[int, float] | None = None,
) -> dict:
    """Target flux in one frame; {'excluded': reason} when it cannot be measured.

    Sources with a coadd flux in this detector are subtracted at that flux; the rest are fitted
    together with the target and a constant."""
    pos = [(r["positions"][epoch_id]["x"], r["positions"][epoch_id]["y"]) for r in rows]
    tx, ty = pos[ti]
    reason = core_state(frame.data, tx, ty)
    if reason:
        return {"excluded": reason}
    fixed = np.zeros_like(frame.data)
    free = [pos[ti]]
    for j, r in enumerate(rows):
        if j == ti:
            continue
        f = neighbour_flux(r, wavelength, frame.detector, centres or {})
        if f is None:
            free.append(pos[j])
        else:
            fixed += f * psf_image(pos[j][0], pos[j][1], sigma, frame.data.shape)
    rest = Frame(frame.epoch, frame.detector, frame.data - fixed, frame.sigma)
    flux, err, model = forced_fluxes(rest, free, sigma)
    f, e = float(flux[0]), float(err[0])
    if not (math.isfinite(f) and math.isfinite(e) and e > 0):
        return {"excluded": "no valid pixels under the PSF"}
    e_tot = math.hypot(e, FLUX_FLOOR * abs(f))
    return {"flux": f * k_mjy, "flux_err": e_tot * k_mjy, "snr": f / e_tot}


def reject_outliers(points: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split points into kept and rejected: a point more than OUTLIER_NSIG robust sigma away from
    the median of the exposures within OUTLIER_WINDOW_UM is rejected."""
    lam = np.array([p["wavelength_um"] for p in points])
    flux = np.array([p["flux"] for p in points])
    err = np.array([p["flux_err"] for p in points])
    keep, out = [], []
    for i, p in enumerate(points):
        near = (np.abs(lam - lam[i]) <= OUTLIER_WINDOW_UM) & (np.arange(len(points)) != i)
        if near.sum() < OUTLIER_MIN_NEIGHBOURS:
            keep.append(p)
            continue
        med = float(np.median(flux[near]))
        mad = 1.4826 * float(np.median(np.abs(flux[near] - med)))
        dev = (flux[i] - med) / math.hypot(mad, err[i])
        if abs(dev) > OUTLIER_NSIG:
            out.append(
                {
                    **{k: p[k] for k in ("obs_id", "epoch_id", "detector")},
                    "reason": f"outlier against exposures at nearby wavelengths ({dev:+.0f} sigma)",
                }
            )
        else:
            keep.append(p)
    return keep, out


def measure_aperture(
    frame: Frame,
    rows: list[dict],
    epoch_id: str,
    ti: int,
    sigma: float,
    k_mjy: float,
    wavelength: float,
    centres: dict[int, float],
) -> dict:
    """Target flux in one single exposure by aperture photometry.

    The single exposures were resampled onto the field grid, which moves a point source by up to
    half a pixel; an aperture keeps its flux where a fixed-position PSF fit does not. Background
    from a sigma-clipped annulus; neighbours inside the aperture subtracted with their coadd flux
    at this wavelength times the fraction of their PSF on the aperture; the sum is divided by the
    fraction of the target's PSF on the valid aperture pixels."""
    pos = [(r["positions"][epoch_id]["x"], r["positions"][epoch_id]["y"]) for r in rows]
    tx, ty = pos[ti]
    reason = core_state(frame.data, tx, ty)
    if reason:
        return {"excluded": reason}
    ny, nx = frame.data.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    r = np.hypot(xx - tx, yy - ty)
    valid = np.isfinite(frame.data)
    ap = (r <= AP_RADIUS_PX) & valid
    ann = (r >= AN_INNER_PX) & (r <= AN_OUTER_PX) & valid
    if ann.sum() < 10:
        return {"excluded": "no background around the target"}
    bg, bg_sd = clipped_stats(frame.data[ann])
    psf_t = psf_image(tx, ty, sigma, frame.data.shape)
    frac = float(psf_t[ap].sum())
    if frac < AP_MIN_VALID:
        return {"excluded": "most of the aperture masked"}
    total = float(np.sum(frame.data[ap] - bg))
    for j, row in enumerate(rows):
        if j == ti or math.hypot(pos[j][0] - tx, pos[j][1] - ty) > AP_RADIUS_PX + 4 * sigma:
            continue
        fj = neighbour_flux(row, wavelength, frame.detector, centres)
        if fj is not None:
            total -= fj * float(psf_image(pos[j][0], pos[j][1], sigma, frame.data.shape)[ap].sum())
    noise = bg_sd if math.isfinite(bg_sd) and bg_sd > 0 else frame.sigma
    n_ap = int(ap.sum())
    f = total / frac
    e = noise * math.sqrt(n_ap * (1 + n_ap / max(int(ann.sum()), 1))) / frac
    e_tot = math.hypot(e, FLUX_FLOOR * abs(f))
    return {"flux": f * k_mjy, "flux_err": e_tot * k_mjy, "snr": f / e_tot}


def _num(v: float, sig: int = 4) -> float:
    return float(f"{v:.{sig}g}")


def spectrum(target, manifest, rows, ti, sig, exposures: ExposureSet) -> dict:
    exp_manifest = exposures.manifest
    for key in ("nx", "ny", "pixscale_arcsec"):
        if exp_manifest[key] != manifest[key]:
            raise SystemExit(f"{target}: exposure grid differs from the coadd grid ({key})")
    known = {e["epoch_id"] for e in manifest["epochs"]}
    centres = {int(d["detector"]): 0.5 * (d["lambda_min_um"] + d["lambda_max_um"]) for d in manifest["detectors"]}
    k = mjy_per_unit(manifest)
    data, excluded = [], []
    n = 0
    for e in exp_manifest["epochs"]:
        if e["epoch_id"] not in known:
            raise SystemExit(f"{target}: exposure epoch {e['epoch_id']} is not in the coadd manifest")
    for frame, (eid, f) in zip(exposures.frames, exposures.meta, strict=True):
        n += 1
        base = {"obs_id": f.get("obs_id"), "epoch_id": eid, "detector": int(f["detector"])}
        if not (math.isfinite(frame.sigma) and frame.sigma > 0):
            excluded.append({**base, "reason": "empty exposure"})
            continue
        m = measure_aperture(frame, rows, eid, ti, sig[int(f["detector"])], k, float(f["wavelength_um"]), centres)
        if "excluded" in m:
            excluded.append({**base, "reason": m["excluded"]})
            continue
        data.append(
            {
                "wavelength_um": round(float(f["wavelength_um"]), 4),
                "bandwidth_um": round(float(f["bandwidth_um"]), 4),
                "flux": _num(m["flux"]),
                "flux_err": _num(m["flux_err"]),
                "snr": round(m["snr"], 1),
                "detected": m["snr"] >= DETECT_SNR,
                "mjd": round(float(f["mjd_avg"]), 5),
                **base,
            }
        )
    data.sort(key=lambda r: (r["wavelength_um"], r["mjd"]))
    data, rejected = reject_outliers(data)
    excluded += rejected
    return {
        "target_id": target.target_id,
        "name": target.name,
        "kind": "spectrum",
        "generated_by": GENERATED_BY,
        "data_release": manifest.get("data_release"),
        "method": "Aperture photometry (1.5 px radius, 4-7 px background annulus) of the target in each "
        "exposure, corrected by the PSF fraction on the aperture; neighbours inside the aperture "
        "subtracted with their coadd fluxes interpolated in wavelength. One point per exposure at its "
        "wavelength at the target's position. Errors include a 5 % systematic floor; exposures more than "
        "5 robust sigma from those at nearby wavelengths are rejected.",
        "x": "wavelength_um",
        "flux_unit": "mJy",
        "psf_sigma_px": {str(d): round(s, 3) for d, s in sig.items()},
        "n_exposures": n,
        "n_points": len(data),
        "n_detected": sum(1 for r in data if r["detected"]),
        "data": data,
        "excluded": excluded,
    }


def _weighted(values: np.ndarray, errors: np.ndarray) -> tuple[float, float]:
    """Weighted mean after a 5-sigma clip; error is the larger of formal and scatter/sqrt(n)."""
    keep = np.ones(len(values), bool)
    for _ in range(3):
        w = 1.0 / errors[keep] ** 2
        mean = float(np.sum(values[keep] * w) / w.sum())
        scatter = 1.4826 * float(np.median(np.abs(values[keep] - mean))) if keep.sum() > 2 else 0.0
        new = np.abs(values - mean) <= OUTLIER_NSIG * np.hypot(errors, scatter)
        if new.sum() < 2 or (new == keep).all():
            break
        keep = new
    w = 1.0 / errors[keep] ** 2
    mean = float(np.sum(values[keep] * w) / w.sum())
    formal = float(1.0 / math.sqrt(w.sum()))
    n = int(keep.sum())
    spread = float(np.std(values[keep], ddof=1)) / math.sqrt(n) if n > 2 else 0.0
    return mean, max(formal, spread)


def lightcurve(target, manifest, spec: dict) -> dict:
    """Brightness on each date relative to the target's own mean spectrum at the same wavelength.

    Each date samples different wavelengths, so absolute fluxes of different dates are not
    comparable; dividing every exposure by the median flux of all exposures (any date) within
    LC_WINDOW_UM removes the spectral shape and leaves the change between dates."""
    pts = [r for r in spec["data"] if r["snr"] >= LC_MIN_SNR]
    lam = np.array([r["wavelength_um"] for r in pts])
    flux = np.array([r["flux"] for r in pts])
    ratios = []
    for i, r in enumerate(pts):
        near = np.abs(lam - lam[i]) <= LC_WINDOW_UM
        if near.sum() < LC_MIN_NEIGHBOURS:
            continue
        model = float(np.median(flux[near]))
        if model <= 0:
            continue
        ratios.append({**r, "ratio": r["flux"] / model, "ratio_err": r["flux_err"] / model})

    def summarize(group: list[dict], key: str) -> list[dict]:
        out = []
        for eid in sorted({g["epoch_id"] for g in group}):
            sel = [g for g in group if g["epoch_id"] == eid]
            if len(sel) < LC_MIN_PER_DATE:
                continue
            mean, err = _weighted(np.array([g["ratio"] for g in sel]), np.array([g["ratio_err"] for g in sel]))
            epoch = next(e for e in manifest["epochs"] if e["epoch_id"] == eid)
            out.append(
                {
                    "mjd": round(float(np.mean([g["mjd"] for g in sel])), 3),
                    "date_iso": epoch.get("date_iso"),
                    "epoch_id": eid,
                    "flux": round(mean, 4),
                    "flux_err": round(err, 4),
                    "n_exposures": len(sel),
                    "wavelength_min_um": min(g["wavelength_um"] for g in sel),
                    "wavelength_max_um": max(g["wavelength_um"] for g in sel),
                    **({"detector": int(key)} if key != "all" else {}),
                }
            )
        return out

    data = summarize(ratios, "all")
    by_det = {}
    for d in sorted({r["detector"] for r in ratios}):
        rows = summarize([r for r in ratios if r["detector"] == d], str(d))
        if rows:
            by_det[str(d)] = rows
    # a real change of brightness shows in every detector; detectors that disagree on a date point
    # to a calibration or data-release difference, not to variability
    for point in data:
        vals = [
            (r["flux"], r["flux_err"]) for rows in by_det.values() for r in rows if r["epoch_id"] == point["epoch_id"]
        ]
        if len(vals) >= 2:
            v = np.array([a for a, _ in vals])
            e = np.array([b for _, b in vals])
            chi2 = float(np.sum(((v - point["flux"]) / e) ** 2) / (len(v) - 1))
            point["detector_chi2"] = round(chi2, 1)
            point["detectors_agree"] = chi2 <= LC_MAX_DET_CHI2
    disagree = [p["epoch_id"] for p in data if p.get("detectors_agree") is False]
    return {
        "target_id": target.target_id,
        "name": target.name,
        "kind": "lightcurve",
        "generated_by": GENERATED_BY,
        "data_release": manifest.get("data_release"),
        "method": "Each exposure of the spectrum with SNR >= 5 is divided by the median flux of all exposures "
        f"within {LC_WINDOW_UM} um of its wavelength (any date); the ratios of one date are averaged "
        "(weighted, 5-sigma clipped). 1.0 is the target's mean brightness; a date at 0.8 is 20 % fainter. "
        "This removes the spectral shape: each date samples different wavelengths.",
        "x": "mjd",
        "flux_unit": "relative to the mean spectrum at the same wavelength",
        "data": data,
        "by_detector": by_det,
        "n_exposures_used": len(ratios),
        "warning": (
            f"The detectors disagree on {', '.join(disagree)}: the change is not the same at all wavelengths "
            "(colour-dependent variability, or a calibration or data-release difference between dates); "
            "see by_detector."
            if disagree
            else None
        ),
    }


def catalog_check(spec: dict, catalogs: dict | None, target_row: dict) -> str:
    """Median spectrum flux near W1 and W2 against the CatWISE magnitudes of the target."""
    name = (target_row.get("catalog") or {}).get("catwise_id")
    wise = next((w for w in (catalogs or {}).get("wise", []) if w.get("name") == name), None)
    if not wise:
        return "no CatWISE counterpart"
    out = []
    for band, (lam, zero) in WISE_ZERO_JY.items():
        mag = wise.get(band)
        pts = [r["flux"] for r in spec["data"] if abs(r["wavelength_um"] - lam) < 0.15]
        if mag is None or not pts:
            continue
        cat = zero * 10 ** (-mag / 2.5) * 1e3
        out.append(f"{band.upper()} {cat:.3g} mJy vs SPHEREx {np.median(pts):.3g} mJy ({len(pts)} pts)")
    return "; ".join(out) or "no points near W1/W2"


def set_manifest_urls(path: Path, target_id: str) -> bool:
    """Fill spectrum_url and lightcurve_url in place, keeping the file's formatting."""
    text = path.read_text(encoding="utf-8")
    new = text
    for key, name in (("spectrum_url", "spectrum.json"), ("lightcurve_url", "lightcurve.json")):
        new = re.sub(rf'"{key}": (null|"[^"]*")', f'"{key}": "/static/fields/{target_id}/{name}"', new, count=1)
    if new != text:
        path.write_text(new, encoding="utf-8")
    return new != text


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--exposures", required=True, type=Path, help="folder with <target>/manifest.json")
    ap.add_argument("--copy-to", type=Path, action="append", default=[], help="also write into <dir>/<target>/")
    ap.add_argument("targets", nargs="*")
    args = ap.parse_args(argv)

    settings = get_settings()
    store = StaticStore(settings.fields_dir, settings.targets_file)
    refs = [store.resolve(a) for a in args.targets] if args.targets else store.fields()
    if any(ref is None or not ref.target_id for ref in refs):
        print("unknown field", file=sys.stderr)
        return 2
    sets = {ref.field_id: ExposureSet(args.exposures / ref.folder, store.manifest(ref.field_id)) for ref in refs}
    exp_sig = exposure_psf_sigmas(list(sets.values()), PSF_SIGMA_DEFAULT)
    print("single-exposure PSF sigma (px):", {d: round(s, 3) for d, s in exp_sig.items()})
    for ref in refs:
        target = store.targets[ref.target_id]
        field_dir = settings.fields_dir / ref.folder
        manifest = store.manifest(ref.field_id)
        sources = json.loads((field_dir / "sources.json").read_text(encoding="utf-8"))
        rows = sources["sources"]
        ti = next(i for i, r in enumerate(rows) if r["is_target"])
        spec = spectrum(target, manifest, rows, ti, exp_sig, sets[ref.field_id])
        curve = lightcurve(target, manifest, spec)
        for out_dir in [field_dir, *[d / ref.folder for d in args.copy_to]]:
            (out_dir / "spectrum.json").write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8")
            (out_dir / "lightcurve.json").write_text(json.dumps(curve, indent=1) + "\n", encoding="utf-8")
            set_manifest_urls(out_dir / "manifest.json", ref.target_id)
        print(
            f"{ref.field_id}: spectrum {spec['n_points']}/{spec['n_exposures']} exposures "
            f"({spec['n_detected']} detected, {len(spec['excluded'])} excluded); "
            f"light curve {len(curve['data'])} dates from {curve['n_exposures_used']} exposures"
            f"{' (WARNING: ' + curve['warning'] + ')' if curve['warning'] else ''}; "
            f"check: {catalog_check(spec, store.read_json(ref.field_id, 'catalogs.json'), rows[ti])}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
