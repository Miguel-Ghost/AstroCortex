"""Synthetic SPHEREx-like exposures for tests and demo data (no network needed).

Each file mimics the real layout: HDUs IMAGE, FLAGS, VARIANCE, ZODI, a celestial WCS
with its own pointing and rotation, and MJD-AVG / DETECTOR header keys.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from . import PIXSCALE_ARCSEC
from .targets import Target, propagate

# Relative brightness per detector (illustrative): cold brown dwarfs appear only in the red bands.
SED = {
    "cold_brown_dwarf": {1: 0.02, 2: 0.05, 3: 0.15, 4: 0.4, 5: 1.5, 6: 1.2},
    "star": {1: 1.0, 2: 0.9, 3: 0.7, 4: 0.4, 5: 0.25, 6: 0.2},
}
DEFAULT_EPOCHS_MJD = (60820.5, 61005.5, 61190.5)  # 2025-05-25, 2025-11-26, 2026-05-30
VARIABILITY = (1.0, 0.5, 1.4)


def make_wcs(
    ra0: float, dec0: float, rot_deg: float, shape: tuple[int, int], pixscale_arcsec: float = PIXSCALE_ARCSEC
) -> WCS:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.cunit = ["deg", "deg"]
    wcs.wcs.crval = [ra0, dec0]
    wcs.wcs.crpix = [shape[1] / 2.0 + 0.5, shape[0] / 2.0 + 0.5]
    s = pixscale_arcsec / 3600.0
    th = math.radians(rot_deg)
    wcs.wcs.cdelt = [-s, s]
    wcs.wcs.pc = [[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]]
    return wcs


def make_exposure(
    path: Path,
    *,
    pointing: tuple[float, float],
    rot_deg: float,
    mjd: float,
    detector: int,
    sources: list[tuple[float, float, float]],
    shape: tuple[int, int] = (96, 96),
    noise: float = 0.01,
    psf_sigma_px: float = 0.9,
    zodi_level: float = 0.5,
    seed: int = 0,
) -> Path:
    rng = np.random.default_rng(seed)
    wcs = make_wcs(pointing[0], pointing[1], rot_deg, shape)
    yy, xx = np.mgrid[0 : shape[0], 0 : shape[1]].astype(float)
    zodi = zodi_level + 0.002 * (xx - shape[1] / 2) + 0.001 * (yy - shape[0] / 2)
    image = zodi + rng.normal(0.0, noise, shape)
    for ra, dec, flux in sources:
        x, y = wcs.world_to_pixel_values(ra, dec)
        image += flux * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * psf_sigma_px**2))
    variance = np.full(shape, noise**2)
    flags = np.zeros(shape, dtype=np.int32)
    hits = rng.integers(0, shape[0], size=(3, 2))
    flags[hits[:, 0], hits[:, 1]] = 1  # a few flagged pixels, like cosmic-ray hits

    header = wcs.to_header()
    header["MJD-AVG"] = mjd
    header["DETECTOR"] = detector
    header["BUNIT"] = "MJy / sr"
    hdus = [fits.PrimaryHDU()]
    for name, data in (
        ("IMAGE", image.astype(np.float32)),
        ("FLAGS", flags),
        ("VARIANCE", variance.astype(np.float32)),
        ("ZODI", zodi.astype(np.float32)),
    ):
        hdus.append(fits.ImageHDU(data=data, header=header, name=name))
    fits.HDUList(hdus).writeto(path, overwrite=True)
    return path


def synthetic_exposures(
    target: Target,
    out_dir: Path,
    *,
    epochs_mjd=DEFAULT_EPOCHS_MJD,
    detectors=(1, 2, 3, 4, 5, 6),
    per_epoch: int = 2,
    n_field_stars: int = 4,
    red_static: int = 0,
    base_flux: float = 1.0,
    seed: int = 0,
) -> tuple[list[Path], list[tuple[float, float, float]]]:
    """Exposures of `target` with fixed field sources; returns the file paths and the sources (ra, dec, flux).

    The first `n_field_stars` sources have a stellar SED; the last `red_static` ones have a cold-dwarf
    SED but do not move (a source the engine must send to review).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    ra_c, dec_c = propagate(target, float(np.median(epochs_mjd)))
    deg_per_px = PIXSCALE_ARCSEC / 3600.0
    stars = []
    for _ in range(n_field_stars + red_static):
        dx, dy = rng.uniform(-11, 11, size=2)
        if math.hypot(dx, dy) < 4:  # keep stars away from the target
            dx += 6 * math.copysign(1, dx)
        stars.append(
            (
                ra_c - dx * deg_per_px / math.cos(math.radians(dec_c)),
                dec_c + dy * deg_per_px,
                float(rng.uniform(0.3, 1.0)),
            )
        )
    sed = SED.get(target.kind, SED["star"])
    varies = "varies" in target.behavior
    paths = []
    for e, mjd0 in enumerate(epochs_mjd):
        factor = VARIABILITY[e % len(VARIABILITY)] if varies else 1.0
        for det in detectors:
            for k in range(per_epoch):
                mjd = mjd0 + 0.3 * k + 0.01 * det
                ra_t, dec_t = propagate(target, mjd)
                offset = rng.uniform(-20, 20, size=2) * deg_per_px
                pointing = (ra_t + offset[0] / math.cos(math.radians(dec_t)), dec_t + offset[1])
                sources = [(ra_t, dec_t, base_flux * sed[det] * factor)]
                for i, (ra, dec, f) in enumerate(stars):
                    kind = "cold_brown_dwarf" if i >= n_field_stars else "star"
                    sources.append((ra, dec, f * SED[kind][det]))
                path = out_dir / f"{target.target_id}_e{e + 1}_d{det}_{k}.fits"
                make_exposure(
                    path,
                    pointing=pointing,
                    rot_deg=float(rng.uniform(0, 360)),
                    mjd=mjd,
                    detector=det,
                    sources=sources,
                    seed=int(rng.integers(1 << 30)),
                )
                paths.append(path)
    return paths, stars
