"""Read a small zone of a SPHEREx spectral image without downloading the whole file.

Remote files are opened with fsspec block caching and `.section[...]`, so only the
needed blocks travel (31x31 px ~ 1.4 MB instead of ~66 MB per file).
"""
from __future__ import annotations

from dataclasses import dataclass

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS, Sip

FSSPEC_KWARGS = {"block_size": 65536, "cache_type": "blockcache"}


@dataclass
class Cutout:
    image: np.ndarray      # IMAGE - ZODI, NaN outside the detector
    variance: np.ndarray
    flags: np.ndarray      # int bitmask, 0 outside the detector
    wcs: WCS               # celestial WCS of the cutout (shifted, SIP kept)
    mjd: float             # MJD-AVG
    detector: int          # 1..6
    source: str            # file path or URL
    wavelength_um: float | None = None  # at the requested position, if available


def read_section(section, full_shape: tuple[int, int], xc: float, yc: float, size: int,
                 fill: float | int) -> tuple[np.ndarray, tuple[int, int]]:
    """Square `size` x `size` window centred on pixel (xc, yc); pads outside the array with `fill`.

    Returns the window and its (x0, y0) origin in full-image pixel coordinates (0-based).
    """
    ny, nx = full_shape
    half = size // 2
    x0 = int(round(xc)) - half
    y0 = int(round(yc)) - half
    x1, y1 = x0 + size, y0 + size
    dtype = np.float64 if isinstance(fill, float) else np.int64
    out = np.full((size, size), fill, dtype=dtype)
    cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x1, nx), min(y1, ny)
    if cx0 < cx1 and cy0 < cy1:
        out[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0] = section[cy0:cy1, cx0:cx1]
    return out, (x0, y0)


def shift_wcs(wcs: WCS, x0: int, y0: int) -> WCS:
    """WCS of a sub-image whose origin is (x0, y0) in the parent; works with negative origins and SIP."""
    shifted = wcs.deepcopy()
    offset = np.array([x0, y0], dtype=float)
    shifted.wcs.crpix = shifted.wcs.crpix - offset
    if wcs.sip is not None:
        shifted.sip = Sip(wcs.sip.a, wcs.sip.b, wcs.sip.ap, wcs.sip.bp, wcs.sip.crpix - offset)
    return shifted


def wavelength_at(hdul, x: float, y: float) -> float | None:
    """Wavelength (um) at a full-detector pixel using the spectral WCS (key 'W'); None if unavailable."""
    try:
        wcs_w = WCS(hdul["IMAGE"].header, fobj=hdul, key="W")
        wcs_w.sip = None
        value = wcs_w.pixel_to_world(x, y)
        value = value[0] if isinstance(value, (list, tuple)) else value
        return float(u.Quantity(value).to_value(u.um))
    except Exception:  # noqa: BLE001 - optional metadata
        return None


def read_cutout(path_or_url: str, position, size_px: int = 49, remote: bool = True) -> Cutout | None:
    """Read IMAGE, VARIANCE, FLAGS and ZODI around a position. Returns None if it is off the detector.

    `position` is either (ra, dec) in degrees or a callable mjd -> (ra, dec); the callable
    form centres the read on the target propagated to this exposure's MJD-AVG.
    """
    open_kwargs = {"use_fsspec": True, "fsspec_kwargs": FSSPEC_KWARGS} if remote else {}
    with fits.open(path_or_url, **open_kwargs) as hdul:
        header = hdul["IMAGE"].header
        mjd = float(header["MJD-AVG"])
        ra, dec = position(mjd) if callable(position) else position
        wcs = WCS(header)
        ny, nx = int(header["NAXIS2"]), int(header["NAXIS1"])
        x, y = wcs.world_to_pixel(SkyCoord(ra * u.deg, dec * u.deg))
        x, y = float(x), float(y)
        if not (-size_px / 2 < x < nx + size_px / 2 and -size_px / 2 < y < ny + size_px / 2):
            return None
        image, (x0, y0) = read_section(hdul["IMAGE"].section, (ny, nx), x, y, size_px, np.nan)
        zodi, _ = read_section(hdul["ZODI"].section, (ny, nx), x, y, size_px, np.nan)
        variance, _ = read_section(hdul["VARIANCE"].section, (ny, nx), x, y, size_px, np.nan)
        flags, _ = read_section(hdul["FLAGS"].section, (ny, nx), x, y, size_px, 0)
        return Cutout(
            image=image - zodi,
            variance=variance,
            flags=flags,
            wcs=shift_wcs(wcs, x0, y0),
            mjd=mjd,
            detector=int(header["DETECTOR"]),
            source=str(path_or_url),
            wavelength_um=wavelength_at(hdul, x, y) if remote else None,
        )
