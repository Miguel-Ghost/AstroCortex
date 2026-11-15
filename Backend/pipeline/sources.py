"""Sources of a published field, measured on its per-epoch coadds (the .bin files of the manifest).

What a row is: a Gaia DR3 / CatWISE2020 object inside the cutout, with its position at the date of
each epoch, or a SPHEREx detection with no catalog counterpart. Only objects SPHEREx actually sees
(S/N >= VISIBLE_SNR in some detector) become rows; the full catalog stays in catalogs.json for the
map layers. The field's target is always a row.

How it is measured (no training, nothing tuned on the targets):
1. Background and noise per frame: sigma-clipped median and standard deviation.
2. PSF per detector: pixel-integrated circular Gaussian whose width is fitted on bright isolated stars
   of all published fields (SPHEREx is undersampled at 6.2"/px, so the pixel integration matters).
3. Forced photometry: in every frame, the fluxes of all objects are fitted together by linear least
   squares at their positions for that date. Blended neighbours (WISE 0855 and the star 1.4 px from
   it) are separated instead of being summed in an aperture.
4. Residual search: peaks >= DETECT_SNR left in the residual of the epoch-averaged image, away from
   bright stars, are detections without a counterpart; they are added and everything is refitted.
5. Motion: for objects bright enough, the position is fitted in each epoch with the neighbours'
   fluxes free; motion_px is the displacement between the first and last measured epoch, reported
   only when it exceeds 3 sigma (otherwise 0).

methane_index here is F(D5, 3.8-4.4 um) / F(D4, 2.4-3.8 um) from the coadds. Each coadd mixes LVF
wavelengths across its detector, so the narrow 3.20-3.45 um band of rule-v0 is approximated by D4;
the definition travels in sources.json. When D4 is not detected the value is a lower limit.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi
from scipy import optimize, special

from .targets import Target, mjd_to_jyear, position_at_year

PSF_SIGMA_DEFAULT = {1: 0.415, 2: 0.383, 3: 0.391, 4: 0.516, 5: 0.517, 6: 0.522}
VISIBLE_SNR = 3.0  # an object becomes a row when it reaches this S/N in some detector
DETECT_SNR = 5.0  # residual peaks and detection counts
FIT_W1_MAX = 16.5  # catalog objects brighter than this (or G < FIT_G_MAX without W1) enter the fit
FIT_G_MAX = 18.5
BLEND_PX = 0.7  # closer than this, two catalog objects cannot be separated: the fainter is dropped
MATCH_GAIA_WISE_ARCSEC = 2.5
TARGET_MATCH_PX = 1.0
MOTION_MIN_SNR = 10.0  # best-detector S/N per epoch needed to fit a position
POSITION_FLOOR_PX = 0.05  # systematic position error per epoch (PSF model, registration)
FLUX_FLOOR = 0.05  # systematic flux error between epochs (calibration, PSF model)
GAIA_EPOCH_YR = 2016.0
CATWISE_EPOCH_MJD = 57170.0
METHANE_DEFINITION = "F(D5 3.8-4.4 um) / F(D4 2.4-3.8 um), forced PSF photometry on the per-epoch coadds"
KIND_TO_CLASS = {"cold_brown_dwarf": "cold_brown_dwarf", "asteroid_comet": "asteroid_comet", "galaxy": "galaxy"}


# ------------------------------------------------------------------------------------------------
@dataclass
class Frame:
    epoch: int
    detector: int
    data: np.ndarray  # background-subtracted, NaN = no data
    sigma: float


@dataclass
class Obj:
    key: str
    ra: float  # at the reference epoch of the field
    dec: float
    pmra: float = 0.0  # mas/yr used to place the object at each date
    pmdec: float = 0.0
    ref_year: float = 0.0  # epoch of (ra0, dec0)
    ra0: float = 0.0
    dec0: float = 0.0
    gaia: dict | None = None
    wise: dict | None = None
    is_target: bool = False
    detected_only: bool = False
    w1: float | None = None
    g: float | None = None
    xy: dict[int, tuple[float, float]] = field(default_factory=dict)  # epoch -> fitted/predicted x, y

    def mag(self) -> float | None:
        """W1, or G - 1.5 (rough G - W1 of field stars) when there is no W1: only to rank and cut."""
        if self.w1 is not None:
            return self.w1
        if self.g is not None:
            return self.g - 1.5
        return None

    def brightness(self) -> float:
        if self.is_target:
            return -99.0  # the target always enters the fit first
        m = self.mag()
        return 99.0 if m is None else m


# ------------------------------------------------------------------------------------------------
def clipped_stats(a: np.ndarray, nsig: float = 3.0, iters: int = 6) -> tuple[float, float]:
    v = a[np.isfinite(a)]
    if v.size < 10:
        return 0.0, float("nan")
    for _ in range(iters):
        mu, s = np.median(v), np.std(v)
        keep = np.abs(v - mu) < nsig * s
        if keep.all():
            break
        v = v[keep]
    return float(np.median(v)), float(np.std(v))


class Grid:
    """Pixel <-> sky for a north-up, east-left manifest grid (pixel centres at integer x, y)."""

    def __init__(self, manifest: dict):
        self.ra0 = float(manifest["center"]["ra"])
        self.dec0 = float(manifest["center"]["dec"])
        self.pix = float(manifest["pixscale_arcsec"])
        self.nx, self.ny = int(manifest["nx"]), int(manifest["ny"])
        self.cx, self.cy = (self.nx - 1) / 2.0, (self.ny - 1) / 2.0
        self.cosd = math.cos(math.radians(self.dec0))

    def to_xy(self, ra: float, dec: float) -> tuple[float, float]:
        dra = ((ra - self.ra0 + 180.0) % 360.0 - 180.0) * self.cosd * 3600.0
        return self.cx - dra / self.pix, self.cy - (dec - self.dec0) * 3600.0 / self.pix

    def to_sky(self, x: float, y: float) -> tuple[float, float]:
        dec = self.dec0 - (y - self.cy) * self.pix / 3600.0
        ra = self.ra0 - (x - self.cx) * self.pix / 3600.0 / self.cosd
        return ra % 360.0, dec

    def inside(self, x: float, y: float, margin: float = 0.5) -> bool:
        return -margin <= x <= self.nx - 1 + margin and -margin <= y <= self.ny - 1 + margin


_yy, _xx = np.mgrid[0:64, 0:64]


def psf_image(x0: float, y0: float, sigma: float, shape: tuple[int, int]) -> np.ndarray:
    """Pixel-integrated circular Gaussian with unit total flux."""
    ny, nx = shape
    k = 1.0 / (math.sqrt(2.0) * sigma)
    xs, ys = np.arange(nx), np.arange(ny)
    ex = 0.5 * (special.erf((xs - x0 + 0.5) * k) - special.erf((xs - x0 - 0.5) * k))
    ey = 0.5 * (special.erf((ys - y0 + 0.5) * k) - special.erf((ys - y0 - 0.5) * k))
    return np.outer(ey, ex)


def forced_fluxes(
    frame: Frame, positions: list[tuple[float, float]], sigma_psf: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fluxes and errors of all objects at fixed positions + a constant; returns (flux, err, model)."""
    data = frame.data
    good = np.isfinite(data)
    k = len(positions)
    cols = [psf_image(x, y, sigma_psf, data.shape)[good] for x, y in positions]
    cols.append(np.ones(int(good.sum())))
    design = np.column_stack(cols)
    flux = np.full(k, np.nan)
    err = np.full(k, np.nan)
    if good.sum() <= k + 1:
        return flux, err, np.zeros_like(data)
    sol, *_ = np.linalg.lstsq(design, data[good], rcond=None)
    try:
        cov = np.linalg.pinv(design.T @ design) * frame.sigma**2
        e = np.sqrt(np.clip(np.diag(cov), 0, None))
    except np.linalg.LinAlgError:
        e = np.full(k + 1, np.nan)
    # a source whose PSF footprint is all NaN (off the frame or masked) has no measurement
    for i, (x, y) in enumerate(positions):
        footprint = psf_image(x, y, sigma_psf, data.shape)
        if footprint[good].sum() < 0.3:
            sol[i], e[i] = np.nan, np.nan
    model = np.zeros_like(data)
    for i, (x, y) in enumerate(positions):
        if np.isfinite(sol[i]):
            model += sol[i] * psf_image(x, y, sigma_psf, data.shape)
    model += sol[-1]
    return sol[:k], e[:k], model


# ------------------------------------------------------------------------------------------------
class FieldMeasurer:
    def __init__(self, field_dir: Path, manifest: dict):
        self.dir = Path(field_dir)
        self.manifest = manifest
        self.grid = Grid(manifest)
        self.epochs = manifest["epochs"]
        self.ref_mjd = float(manifest.get("center_ref_mjd") or manifest.get("center_mjd") or self.epochs[0]["mjd_avg"])
        self.ref_year = mjd_to_jyear(self.ref_mjd)
        self.frames: list[Frame] = []
        for e, epoch in enumerate(self.epochs):
            for f in epoch["frames"]:
                url = f.get("data_url")
                if not url:
                    continue
                path = self.dir / Path(url).name
                if not path.is_file():
                    continue
                raw = np.fromfile(path, dtype="<f4").reshape(self.grid.ny, self.grid.nx).astype(float)
                mu, s = clipped_stats(raw)
                if not np.isfinite(s) or s <= 0:
                    continue
                self.frames.append(Frame(e, int(f["detector"]), raw - mu, s))
        self.detectors = sorted({fr.detector for fr in self.frames})

    def epoch_year(self, e: int) -> float:
        return mjd_to_jyear(float(self.epochs[e]["mjd_avg"]))

    # -- PSF ------------------------------------------------------------------------------------
    def fit_psf_sigmas(self) -> dict[int, list[float]]:
        """Gaussian widths of bright, isolated, unsaturated stars in this field, per detector."""
        out: dict[int, list[float]] = {d: [] for d in self.detectors}
        for fr in self.frames:
            snr = np.nan_to_num(fr.data / fr.sigma)
            peaks = np.argwhere((snr == ndi.maximum_filter(snr, size=9)) & (snr > 40))
            for y, x in peaks:
                if not (3 <= x <= self.grid.nx - 4 and 3 <= y <= self.grid.ny - 4):
                    continue
                win = (slice(y - 3, y + 4), slice(x - 3, x + 4))
                patch = fr.data[win]
                if np.isnan(patch).any():
                    continue

                def resid(p, patch=patch, x=x, y=y, noise=fr.sigma):
                    model = p[2] * psf_image(p[0] - (x - 3), p[1] - (y - 3), p[3], patch.shape) + p[4]
                    return ((patch - model) / noise).ravel()

                try:
                    sol = optimize.least_squares(
                        resid,
                        [x, y, float(np.nansum(patch)), 0.5, 0.0],
                        bounds=([x - 1.5, y - 1.5, 0, 0.2, -np.inf], [x + 1.5, y + 1.5, np.inf, 2.0, np.inf]),
                    )
                except ValueError:
                    continue
                out[fr.detector].append(float(sol.x[3]))
        return out

    # -- positions ------------------------------------------------------------------------------
    def place(self, obj: Obj) -> None:
        """Predicted x, y of an object at every epoch from its catalog proper motion."""
        for e in range(len(self.epochs)):
            if obj.detected_only:
                obj.xy.setdefault(e, self.grid.to_xy(obj.ra, obj.dec))
                continue
            dt = self.epoch_year(e) - obj.ref_year
            dec = obj.dec0 + obj.pmdec * dt / 3.6e6
            ra = obj.ra0 + obj.pmra * dt / 3.6e6 / math.cos(math.radians(dec))
            obj.xy[e] = self.grid.to_xy(ra, dec)

    def ref_xy(self, obj: Obj) -> tuple[float, float]:
        return self.grid.to_xy(obj.ra, obj.dec)

    # -- photometry -----------------------------------------------------------------------------
    def photometry(self, objs: list[Obj], sig: dict[int, float]) -> dict[tuple[int, int], tuple]:
        """{(epoch, detector): (flux[k], err[k], residual)} for all objects at their positions."""
        result = {}
        for fr in self.frames:
            pos = [o.xy[fr.epoch] for o in objs]
            flux, err, model = forced_fluxes(fr, pos, sig[fr.detector])
            result[(fr.epoch, fr.detector)] = (flux, err, fr.data - model)
        return result

    def combined(self, phot: dict, k: int, det: int) -> tuple[float, float]:
        f, w = [], []
        for (_e, d), (flux, err, _) in phot.items():
            if d == det and np.isfinite(flux[k]) and np.isfinite(err[k]) and err[k] > 0:
                f.append(flux[k])
                w.append(1.0 / err[k] ** 2)
        if not w:
            return float("nan"), float("nan")
        w = np.asarray(w)
        return float(np.sum(np.asarray(f) * w) / w.sum()), float(1.0 / math.sqrt(w.sum()))

    def residual_peaks(
        self, phot: dict, objs: list[Obj], combined_snr: list[float]
    ) -> list[tuple[float, float, float]]:
        """Peaks of the epoch-averaged residual per detector that no object explains."""
        peaks = []
        for det in self.detectors:
            stack, wsum = np.zeros((self.grid.ny, self.grid.nx)), np.zeros((self.grid.ny, self.grid.nx))
            for fr in self.frames:
                if fr.detector != det:
                    continue
                res = phot[(fr.epoch, det)][2]
                good = np.isfinite(res)
                w = 1.0 / fr.sigma**2
                stack[good] += res[good] * w
                wsum[good] += w
            with np.errstate(invalid="ignore", divide="ignore"):
                snr = np.where(wsum > 0, stack / np.sqrt(wsum), 0.0)
            snr = np.nan_to_num(snr)
            cand = np.argwhere((snr == ndi.maximum_filter(snr, size=3)) & (snr >= DETECT_SNR))
            for y, x in cand:
                y0, y1, x0, x1 = max(0, y - 1), min(self.grid.ny, y + 2), max(0, x - 1), min(self.grid.nx, x + 2)
                patch = np.clip(snr[y0:y1, x0:x1], 0, None)
                yy, xx = np.mgrid[y0:y1, x0:x1]
                cx, cy = float((patch * xx).sum() / patch.sum()), float((patch * yy).sum() / patch.sum())
                if self._near_bright(cx, cy, objs, combined_snr):
                    continue
                peaks.append((cx, cy, float(snr[y, x])))
        # merge across detectors (greedy by S/N, 1 px)
        peaks.sort(key=lambda p: -p[2])
        merged: list[tuple[float, float, float]] = []
        for p in peaks:
            if all(math.hypot(p[0] - q[0], p[1] - q[1]) > 1.0 for q in merged):
                merged.append(p)
        return merged

    def _near_bright(self, x: float, y: float, objs: list[Obj], combined_snr: list[float]) -> bool:
        """Residuals around bright stars are PSF mismatch, not sources."""
        for o, s in zip(objs, combined_snr, strict=True):
            ox, oy = self.ref_xy(o)
            d = math.hypot(x - ox, y - oy)
            if d < 1.0 or (s > 50 and d < 2.5) or (s > 300 and d < 4.0) or (s > 3000 and d < 6.0):
                return True
        return False

    # -- motion ---------------------------------------------------------------------------------
    def fit_position(self, fr: Frame, objs: list[Obj], k: int, sig: float) -> tuple[float, float, float] | None:
        """(x, y, sigma_xy) of object k in one frame, neighbours at their positions with free fluxes."""
        x0, y0 = objs[k].xy[fr.epoch]
        near = [
            i for i, o in enumerate(objs) if i != k and math.hypot(o.xy[fr.epoch][0] - x0, o.xy[fr.epoch][1] - y0) < 6
        ]
        ys, xs = (
            slice(max(0, int(y0) - 4), min(fr.data.shape[0], int(y0) + 5)),
            slice(max(0, int(x0) - 4), min(fr.data.shape[1], int(x0) + 5)),
        )
        patch = fr.data[ys, xs]
        good = np.isfinite(patch)
        if good.sum() < 20:
            return None
        ox, oy = xs.start, ys.start

        def resid(p):
            cols = [psf_image(p[0] - ox, p[1] - oy, sig, patch.shape)[good]]
            cols += [
                psf_image(objs[i].xy[fr.epoch][0] - ox, objs[i].xy[fr.epoch][1] - oy, sig, patch.shape)[good]
                for i in near
            ]
            cols.append(np.ones(int(good.sum())))
            a = np.column_stack(cols)
            sol, *_ = np.linalg.lstsq(a, patch[good], rcond=None)
            return (patch[good] - a @ sol) / fr.sigma

        try:
            sol = optimize.least_squares(resid, [x0, y0], bounds=([x0 - 2, y0 - 2], [x0 + 2, y0 + 2]))
        except ValueError:
            return None
        if max(abs(sol.x[0] - x0), abs(sol.x[1] - y0)) > 1.8:
            return None  # ran to the bounds: the position is not constrained by this frame
        jac = sol.jac
        try:
            cov = np.linalg.inv(jac.T @ jac)
            s = float(math.sqrt(max(cov[0, 0], cov[1, 1])))
        except np.linalg.LinAlgError:
            return None
        return float(sol.x[0]), float(sol.x[1]), s


# ------------------------------------------------------------------------------------------------
def catalog_objects(meas: FieldMeasurer, catalogs: dict | None, target: Target | None) -> tuple[list[Obj], bool]:
    """Gaia and CatWISE merged into one list of objects inside the cutout, placed at each epoch."""
    grid = meas.grid
    objs: list[Obj] = []
    checked = catalogs is not None
    if checked:
        gaia = [
            {**g, "ra_cat": g.get("ra_cat", g["ra"]), "dec_cat": g.get("dec_cat", g["dec"])}
            for g in catalogs.get("gaia", [])
        ]
        wise = [
            {**w, "ra_cat": w.get("ra_cat", w["ra"]), "dec_cat": w.get("dec_cat", w["dec"])}
            for w in catalogs.get("wise", [])
        ]
        catwise_year = mjd_to_jyear(CATWISE_EPOCH_MJD)

        def at_ref(ra, dec, pmra, pmdec, year):
            dt = meas.ref_year - year
            d = dec + (pmdec or 0.0) * dt / 3.6e6
            r = ra + (pmra or 0.0) * dt / 3.6e6 / math.cos(math.radians(d))
            return r, d

        used_wise: set[int] = set()
        wise_ref = [at_ref(w["ra_cat"], w["dec_cat"], _pm(w, "pmra"), _pm(w, "pmdec"), catwise_year) for w in wise]
        for g in gaia:
            ra, dec = at_ref(g["ra_cat"], g["dec_cat"], g.get("pmra"), g.get("pmdec"), GAIA_EPOCH_YR)
            x, y = grid.to_xy(ra, dec)
            if not grid.inside(x, y, margin=1.0):
                continue
            match = None
            best = MATCH_GAIA_WISE_ARCSEC
            for j, (wr, wd) in enumerate(wise_ref):
                if j in used_wise:
                    continue
                sep = _sep_arcsec(ra, dec, wr, wd)
                if sep < best:
                    match, best = j, sep
            w = wise[match] if match is not None else None
            if match is not None:
                used_wise.add(match)
            objs.append(
                Obj(
                    key=f"gaia:{g['source_id']}",
                    ra=ra,
                    dec=dec,
                    pmra=g.get("pmra") or 0.0,
                    pmdec=g.get("pmdec") or 0.0,
                    ref_year=GAIA_EPOCH_YR,
                    ra0=g["ra_cat"],
                    dec0=g["dec_cat"],
                    gaia=g,
                    wise=w,
                    w1=w.get("w1") if w else None,
                    g=g.get("g_mag"),
                )
            )
        for j, w in enumerate(wise):
            if j in used_wise:
                continue
            ra, dec = wise_ref[j]
            x, y = grid.to_xy(ra, dec)
            if not grid.inside(x, y, margin=1.0):
                continue
            objs.append(
                Obj(
                    key=f"catwise:{w['name']}",
                    ra=ra,
                    dec=dec,
                    pmra=_pm(w, "pmra"),
                    pmdec=_pm(w, "pmdec"),
                    ref_year=catwise_year,
                    ra0=w["ra_cat"],
                    dec0=w["dec_cat"],
                    wise=w,
                    w1=w.get("w1"),
                )
            )

    # the field's target: its catalog counterpart gets the target's astrometry, or it is added
    if target is not None:
        t_ra, t_dec = position_at_year(target, meas.ref_year)
        tx, ty = grid.to_xy(t_ra, t_dec)
        best_i, best_d = None, TARGET_MATCH_PX
        for i, o in enumerate(objs):
            ox, oy = grid.to_xy(o.ra, o.dec)
            d = math.hypot(ox - tx, oy - ty)
            if d < best_d:
                best_i, best_d = i, d
        if best_i is None:
            objs.append(Obj(key=f"target:{target.target_id}", ra=t_ra, dec=t_dec))
            best_i = len(objs) - 1
        t = objs[best_i]
        t.is_target = True
        t.ra, t.dec = t_ra, t_dec
        t.ra0, t.dec0, t.ref_year = target.ra, target.dec, target.ref_epoch_yr
        t.pmra, t.pmdec = target.pmra_masyr, target.pmdec_masyr

    for o in objs:
        meas.place(o)
    return objs, checked


def _pm(w: dict, key: str) -> float:
    """CatWISE proper motion only when it is significant (faint CatWISE motions are mostly noise)."""
    value, sig = w.get(key), w.get("sig_pm")
    if value is None:
        return 0.0
    if sig is not None and sig > 0 and abs(value) < 3 * sig:
        return 0.0
    return float(value)


def _sep_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    dra = ((ra1 - ra2 + 180.0) % 360.0 - 180.0) * math.cos(math.radians((dec1 + dec2) / 2))
    return math.hypot(dra, dec1 - dec2) * 3600.0


def select_for_fit(meas: FieldMeasurer, objs: list[Obj]) -> list[Obj]:
    """Objects bright enough to matter; unresolvable pairs keep only the brighter one."""
    cand = [
        o
        for o in objs
        if o.is_target
        or (o.w1 is not None and o.w1 < FIT_W1_MAX)
        or (o.w1 is None and o.g is not None and o.g < FIT_G_MAX)
    ]
    cand.sort(key=lambda o: o.brightness())
    kept: list[Obj] = []
    for o in cand:
        ox, oy = meas.ref_xy(o)
        clash = False
        for k in kept:
            kx, ky = meas.ref_xy(k)
            d = math.hypot(ox - kx, oy - ky)
            # unresolvable pair, or a faint catalog entry in the glare of a much brighter star
            glare = (
                not o.is_target and o.mag() is not None and k.mag() is not None and d < 3.0 and o.mag() - k.mag() > 5.0
            )
            if (d < BLEND_PX and not (o.is_target or k.is_target)) or glare:
                clash = True
                break
        if not clash:
            kept.append(o)
    # a neighbour that sits on the target at every epoch cannot be separated from it
    target = next((o for o in kept if o.is_target), None)
    if target is not None:
        kept = [
            o
            for o in kept
            if o is target
            or min(math.hypot(o.xy[e][0] - target.xy[e][0], o.xy[e][1] - target.xy[e][1]) for e in target.xy)
            >= BLEND_PX
        ]
    return kept


# ------------------------------------------------------------------------------------------------
def build_sources(field_dir: Path, target: Target | None, catalogs: dict | None, psf_sigma: dict[int, float]) -> dict:
    field_dir = Path(field_dir)
    manifest = json.loads((field_dir / "manifest.json").read_text(encoding="utf-8"))
    meas = FieldMeasurer(field_dir, manifest)
    sig = {d: psf_sigma.get(d, PSF_SIGMA_DEFAULT.get(d, 0.45)) for d in meas.detectors}
    all_objs, checked = catalog_objects(meas, catalogs, target)
    objs = select_for_fit(meas, all_objs)

    # first pass, residual search, second pass
    phot = meas.photometry(objs, sig)
    snr0 = []
    for k in range(len(objs)):
        best = 0.0
        for d in meas.detectors:
            f, e = meas.combined(phot, k, d)
            if np.isfinite(f) and np.isfinite(e) and e > 0:
                best = max(best, f / e)
        snr0.append(best)
    in_fit = {id(o) for o in objs}
    for n, (x, y, _s) in enumerate(meas.residual_peaks(phot, objs, snr0)):
        # a residual peak on a catalog object too faint for the first pass is that object, not a new source
        nearest, best = None, 1.0
        for o in all_objs:
            if id(o) in in_fit:
                continue
            ox, oy = meas.ref_xy(o)
            d = math.hypot(ox - x, oy - y)
            if d < best:
                nearest, best = o, d
        if nearest is not None:
            objs.append(nearest)
            in_fit.add(id(nearest))
            continue
        ra, dec = meas.grid.to_sky(x, y)
        extra = Obj(key=f"spherex:{n}", ra=ra, dec=dec, detected_only=True)
        meas.place(extra)
        objs.append(extra)
    phot = meas.photometry(objs, sig)

    rows = []
    for k, obj in enumerate(objs):
        per_det = {}
        for d in meas.detectors:
            f, e = meas.combined(phot, k, d)
            per_det[d] = (f, e, f / e if np.isfinite(f) and np.isfinite(e) and e > 0 else float("nan"))
        snrs = {d: v[2] for d, v in per_det.items() if np.isfinite(v[2])}
        best_snr = max(snrs.values(), default=0.0)
        if best_snr < VISIBLE_SNR and not obj.is_target:
            continue
        best_det = max(snrs, key=snrs.get) if snrs else None
        rows.append(_row(meas, obj, k, objs, phot, per_det, best_det, sig, checked, target))

    rows.sort(key=lambda r: (not r["is_target"], -r["evidence"]["snr_max"]))
    tid = target.target_id if target else field_dir.name
    for n, r in enumerate(rows):
        r["source_id"] = f"{tid}_s{n:02d}"
    return {
        "field_id": manifest.get("field_id", field_dir.name),
        "synthetic": False,
        "generated_by": "pipeline.sources (forced PSF photometry on the published coadds)",
        "catalogs_checked": checked,
        "catalog_source": (catalogs or {}).get("source"),
        "epoch_mjd": round(meas.ref_mjd, 4),
        "psf_sigma_px": {str(d): round(s, 3) for d, s in sig.items()},
        "methane_index_definition": METHANE_DEFINITION,
        "visible_snr": VISIBLE_SNR,
        "sources": rows,
    }


def _row(meas, obj, k, objs, phot, per_det, best_det, sig, checked, target) -> dict:
    grid = meas.grid
    n_ep = len(meas.epochs)
    # detections per epoch in the best detector
    epoch_snr = {}
    for (e, d), (flux, err, _) in phot.items():
        if d == best_det and np.isfinite(flux[k]) and np.isfinite(err[k]) and err[k] > 0:
            epoch_snr[e] = flux[k] / err[k]
    n_detected = sum(1 for s in epoch_snr.values() if s >= DETECT_SNR)

    # motion measured in SPHEREx
    motion_px, motion_sigma, motion_epochs = None, None, None
    fitted = {}
    if best_det is not None and _isolated(meas, objs, k, phot, best_det):
        for fr in meas.frames:
            if fr.detector == best_det and epoch_snr.get(fr.epoch, 0) >= MOTION_MIN_SNR:
                pos = meas.fit_position(fr, objs, k, sig[best_det])
                if pos is not None:
                    fitted[fr.epoch] = pos
    if len(fitted) >= 2:
        e0, e1 = min(fitted), max(fitted)
        (x0, y0, s0), (x1, y1, s1) = fitted[e0], fitted[e1]
        disp = math.hypot(x1 - x0, y1 - y0)
        motion_sigma = math.hypot(math.hypot(s0, POSITION_FLOOR_PX), math.hypot(s1, POSITION_FLOOR_PX))
        motion_px = round(disp, 2) if disp > 3 * motion_sigma else 0.0
        motion_epochs = [meas.epochs[e0]["epoch_id"], meas.epochs[e1]["epoch_id"]]

    # methane index
    f5, e5, s5 = per_det.get(5, (float("nan"),) * 3)
    f4, e4, s4 = per_det.get(4, (float("nan"),) * 3)
    methane, lower = None, False
    if np.isfinite(s5) and s5 >= 3:
        if np.isfinite(s4) and s4 >= 3:
            methane = f5 / f4
        elif np.isfinite(e4) and e4 > 0:
            methane, lower = f5 / (3 * e4), True

    # variability in the best detector (needs 2+ epochs measured)
    variable = None
    if best_det is not None:
        vals = [
            (flux[k], err[k])
            for (e, d), (flux, err, _) in phot.items()
            if d == best_det and np.isfinite(flux[k]) and err[k] > 0
        ]
        if len(vals) >= 2:
            f = np.array([v[0] for v in vals])
            er = np.hypot(np.array([v[1] for v in vals]), FLUX_FLOOR * np.abs(f))  # calibration floor
            mean = np.average(f, weights=1 / er**2)
            chi2 = float(np.sum(((f - mean) / er) ** 2) / (len(f) - 1))
            amp = float((f.max() - f.min()) / abs(mean)) if mean != 0 else 0.0
            variable = bool(chi2 > 25 and amp > 0.2)

    # masked pixels around the source (saturated cores, no data)
    masked, total, saturated = 0, 0, False
    for fr in meas.frames:
        x, y = obj.xy[fr.epoch]
        ix, iy = int(round(x)), int(round(y))
        if not (0 <= ix < grid.nx and 0 <= iy < grid.ny):
            continue
        win = fr.data[max(0, iy - 1) : iy + 2, max(0, ix - 1) : ix + 2]
        masked += int(np.isnan(win).sum())
        total += win.size
        if np.isnan(fr.data[iy, ix]) and 1 <= ix < grid.nx - 1 and 1 <= iy < grid.ny - 1:
            saturated = True
    flagged = round(masked / total, 3) if total else None
    if saturated:
        variable = None  # the core is masked: epoch-to-epoch fluxes are not reliable enough

    # catalog block (BR-CLS-02: types go to `catalog`, never into the evidence)
    in_gaia = (obj.gaia is not None) if checked else None
    in_catwise = (obj.wise is not None) if checked else None
    pm = None
    if obj.is_target and target is not None:
        pm = {"pmra": round(target.pmra_masyr, 1), "pmdec": round(target.pmdec_masyr, 1)}
    elif obj.gaia is not None and obj.gaia.get("pmra") is not None:
        pm = {"pmra": round(obj.gaia["pmra"], 1), "pmdec": round(obj.gaia["pmdec"], 1)}
    elif obj.wise is not None and (obj.pmra or obj.pmdec):
        pm = {"pmra": round(obj.pmra, 1), "pmdec": round(obj.pmdec, 1)}
    catalog = {
        "gaia_id": obj.gaia["source_id"] if obj.gaia else None,
        "catwise_id": obj.wise["name"] if obj.wise else None,
    }
    if obj.is_target and target is not None:
        catalog.update(
            status="known_typed",
            known_label=KIND_TO_CLASS.get(target.kind, "star"),
            known_source="SIMBAD",
            simbad_type=target.kind,
        )
    elif not checked:
        catalog["status"] = "not_checked"
    elif obj.gaia is not None or obj.wise is not None:
        catalog["status"] = "catalogued_untyped"
    else:
        catalog["status"] = "uncatalogued"

    ref_x, ref_y = grid.to_xy(obj.ra, obj.dec)
    positions = {}
    for e in range(n_ep):
        x, y = obj.xy[e]
        if e in fitted and obj.detected_only:
            x, y = fitted[e][0], fitted[e][1]
        ra, dec = grid.to_sky(x, y)
        positions[meas.epochs[e]["epoch_id"]] = {
            "x": round(x, 2),
            "y": round(y, 2),
            "ra": round(ra, 6),
            "dec": round(dec, 6),
        }

    if obj.is_target and target is not None:
        name = target.name
    elif obj.gaia is not None:
        name = f"Gaia DR3 {obj.gaia['source_id']}"
    elif obj.wise is not None:
        name = f"CWISE {obj.wise['name']}"
    else:
        name = "SPHEREx detection"

    detected_in = sorted(d for d, v in per_det.items() if np.isfinite(v[2]) and v[2] >= DETECT_SNR)
    return {
        "source_id": "",
        "name": name,
        "is_target": obj.is_target,
        "ra": round(obj.ra, 6),
        "dec": round(obj.dec, 6),
        "x": round(ref_x, 2),
        "y": round(ref_y, 2),
        "epoch_mjd": round(meas.ref_mjd, 4),
        "positions": positions,
        "evidence": {
            "motion_px": motion_px,
            "motion_sigma_px": None if motion_sigma is None else round(motion_sigma, 3),
            "motion_epochs": motion_epochs,
            "pm_mas_yr": pm,
            "methane_index": None if methane is None else round(float(methane), 3),
            "methane_index_lower_limit": lower,
            "in_gaia": in_gaia,
            "in_catwise": in_catwise,
            "jpl_match": None,
            "extended": None,
            "variable": variable,
            "flagged_frac": flagged,
            "saturated": saturated,
            "n_epochs_detected": n_detected,
            "detected_in": detected_in,
            "snr_max": round(float(max((v[2] for v in per_det.values() if np.isfinite(v[2])), default=0.0)), 1),
        },
        "photometry": {
            f"D{d}": {"flux": _r(v[0]), "flux_err": _r(v[1]), "snr": _r(v[2], 1)} for d, v in sorted(per_det.items())
        },
        "catalog": catalog,
        "obs_ids": [],
    }


def _isolated(meas: FieldMeasurer, objs: list[Obj], k: int, phot: dict, det: int) -> bool:
    """A position can be fitted when no comparable neighbour is within 2.5 px and no much brighter
    one within 6 px (its PSF wings, which a Gaussian does not model, would pull the centroid)."""
    flux_k = meas.combined(phot, k, det)[0]
    if not np.isfinite(flux_k) or flux_k <= 0:
        return False
    xk, yk = meas.ref_xy(objs[k])
    for i, o in enumerate(objs):
        if i == k:
            continue
        xi, yi = meas.ref_xy(o)
        d = math.hypot(xi - xk, yi - yk)
        if d >= 6.0:
            continue
        flux_i = meas.combined(phot, i, det)[0]
        if not np.isfinite(flux_i):
            continue
        # a neighbour with a catalog position is fitted at that position; only an undetermined one
        # (a bare SPHEREx detection) or a near-coincident one makes the centroid ambiguous
        comparable = flux_i > 0.3 * flux_k and (d < 1.2 or (d < 2.5 and o.detected_only))
        if comparable or flux_i > 20 * flux_k:
            return False
    return True


def _r(value: float, nd: int = 5) -> float | None:
    return None if value is None or not np.isfinite(value) else round(float(value), nd)
