"""Combine the exposures of one epoch and detector into a single, less noisy frame."""

from __future__ import annotations

import numpy as np

PROTECTED_FLAG_WORDS = ("SOURCE", "OUTLIER")


def protected_bits(flag_bits: dict[str, int]) -> int:
    """Bitmask of the flags that must never be excluded (BR-PIPE-01), from the header flag names."""
    mask = 0
    for name, bit in flag_bits.items():
        if any(word in name.upper() for word in PROTECTED_FLAG_WORDS):
            mask |= 1 << bit
    return mask


def coadd(
    images: list[np.ndarray],
    variances: list[np.ndarray],
    flags: list[np.ndarray],
    exclude_bits: int = 0,
    protected: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Inverse-variance weighted mean.

    `exclude_bits`: pixels with any of these FLAGS bits are left out of the mean
    (read the bit meanings from the MSKN*/MSKD* header keys). Keep SOURCE and OUTLIER
    out of this mask: a moving object usually carries them.
    Output flags are the OR of the inputs, for display.
    `protected`: bits that `exclude_bits` may not contain (BR-PIPE-01); raises ValueError if it does.
    """
    if exclude_bits & protected:
        raise ValueError("BR-PIPE-01: SOURCE and OUTLIER flags cannot be excluded from a coadd")
    imgs = np.stack(images).astype(float)
    vars_ = np.stack(variances).astype(float)
    flgs = np.stack(flags).astype(np.int64)
    usable = np.isfinite(imgs) & np.isfinite(vars_) & (vars_ > 0)
    if exclude_bits:
        usable &= (flgs & exclude_bits) == 0
    weights = np.where(usable, 1.0 / np.where(vars_ > 0, vars_, 1.0), 0.0)
    wsum = weights.sum(axis=0)
    num = np.where(usable, imgs * weights, 0.0).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        image = np.where(wsum > 0, num / wsum, np.nan)
        variance = np.where(wsum > 0, 1.0 / wsum, np.nan)
    out_flags = np.bitwise_or.reduce(flgs, axis=0)
    return image, variance, out_flags, len(images)
