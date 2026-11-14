"""Common grid: every cutout of a field is resampled onto the same north-up, east-left grid.

Without this step the blink shows jumps caused by each exposure's own pointing and rotation,
not real motion. The grid centre is FIXED for the whole field (the target propagated to a
reference date); the per-date position goes only into the crosshair.
"""

from __future__ import annotations

import numpy as np
from astropy.wcs import WCS

from .read import Cutout


def make_grid_wcs(ra: float, dec: float, size_px: int, pixscale_arcsec: float) -> WCS:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.cunit = ["deg", "deg"]
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.crpix = [(size_px + 1) / 2.0, (size_px + 1) / 2.0]
    scale = pixscale_arcsec / 3600.0
    wcs.wcs.cdelt = [-scale, scale]  # RA grows to the left (east-left), Dec grows upward
    wcs.pixel_shape = (size_px, size_px)
    return wcs


def reproject_cutout(cutout: Cutout, grid_wcs: WCS, size_px: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Resample image and variance (bilinear) and flags (nearest) onto the grid. NaN where there is no data."""
    from reproject import reproject_interp  # heavy import, only when the pipeline runs

    shape = (size_px, size_px)
    image, _ = reproject_interp((cutout.image, cutout.wcs), grid_wcs, shape_out=shape, order="bilinear")
    variance, _ = reproject_interp((cutout.variance, cutout.wcs), grid_wcs, shape_out=shape, order="bilinear")
    flags_f, _ = reproject_interp(
        (cutout.flags.astype(float), cutout.wcs), grid_wcs, shape_out=shape, order="nearest-neighbor"
    )
    flags = np.where(np.isfinite(flags_f), flags_f, 0).astype(np.int64)
    return image, variance, flags
