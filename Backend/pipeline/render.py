"""Write frames for the frontend: fixed stretch per detector, PNG and float32 data.

Orientation of everything written here: row 0 = north (top), column 0 = east (left).
FITS-style arrays from the grid have row 0 = south, so they are flipped vertically.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def stretch_limits(images: list[np.ndarray], lo: float = 0.5, hi: float = 99.5) -> tuple[float, float]:
    """One (vmin, vmax) for all epochs of a detector, so brightness changes are real and not display effects."""
    values = np.concatenate([img[np.isfinite(img)].ravel() for img in images]) if images else np.array([])
    if values.size == 0:
        return 0.0, 1.0
    vmin, vmax = np.percentile(values, [lo, hi])
    if vmax <= vmin:
        vmax = vmin + 1e-6
    return float(vmin), float(vmax)


def asinh_norm(image: np.ndarray, vmin: float, vmax: float, softening: float = 0.1) -> np.ndarray:
    x = np.clip((image - vmin) / (vmax - vmin), 0.0, 1.0)
    return np.arcsinh(x / softening) / np.arcsinh(1.0 / softening)


def to_north_up(array: np.ndarray) -> np.ndarray:
    return np.flipud(array)


def grid_to_png_xy(x: float, y: float, ny: int) -> tuple[float, float]:
    """Grid (FITS-style, 0-based) pixel -> frontend pixel (row 0 = north)."""
    return x, (ny - 1) - y


def save_png(image: np.ndarray, vmin: float, vmax: float, path: Path) -> None:
    """Grayscale + alpha PNG; alpha = 0 where there is no data (NaN), so the UI can colour it."""
    finite = np.isfinite(image)
    lum = np.where(finite, np.round(asinh_norm(np.where(finite, image, vmin), vmin, vmax) * 255), 0)
    alpha = np.where(finite, 255, 0)
    rgba_la = np.dstack([lum, alpha]).astype(np.uint8)
    Image.fromarray(to_north_up(rgba_la)).save(path, optimize=True)


def save_flags_png(
    flags: np.ndarray, path: Path, color: tuple[int, int, int] = (255, 64, 64), alpha: int = 110
) -> None:
    rgba = np.zeros(flags.shape + (4,), dtype=np.uint8)
    mask = flags != 0
    rgba[mask] = (*color, alpha)
    Image.fromarray(to_north_up(rgba)).save(path, optimize=True)


def save_float32(image: np.ndarray, path: Path) -> None:
    """Little-endian float32, row-major, row 0 = north, NaN = no data (contract 7.2, data_url)."""
    to_north_up(image).astype("<f4").tofile(path)
