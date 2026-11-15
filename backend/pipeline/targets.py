"""Target list and proper-motion propagation."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from astropy.time import Time

DEFAULT_TARGETS_FILE = Path(__file__).resolve().parent.parent / "data" / "targets.json"


@dataclass(frozen=True)
class Target:
    target_id: str
    name: str
    kind: str
    behavior: list[str] = field(hash=False)
    short_description: str = ""
    ra: float = 0.0
    dec: float = 0.0
    ref_epoch_yr: float = 2016.0
    pmra_masyr: float = 0.0  # includes cos(dec)
    pmdec_masyr: float = 0.0
    astrometry_source: str = ""
    verified: bool = False
    autotype: bool = False
    motion_arcsec_yr: float = 0.0
    default_detector: int = 3
    aliases: list[str] = field(default_factory=list, hash=False)
    approx_center: dict = field(default_factory=dict, hash=False)  # centre of the published field

    @property
    def pm_total_masyr(self) -> float:
        return math.hypot(self.pmra_masyr, self.pmdec_masyr)


def load_targets(path: Path | str = DEFAULT_TARGETS_FILE) -> dict[str, Target]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return {row["target_id"]: Target(**row) for row in rows}


def mjd_to_jyear(mjd: float) -> float:
    return float(Time(mjd, format="mjd").jyear)


def jyear_to_mjd(jyear: float) -> float:
    return float(Time(jyear, format="jyear").mjd)


def propagate(target: Target, mjd: float) -> tuple[float, float]:
    """Position of the target at `mjd` with linear proper motion (no parallax). BR-FIELD-05.

    Parallax is ignored on purpose: for Barnard's Star it is 0.55" = 0.09 SPHEREx pixels.
    The linear approximation is far below a pixel for these targets over ~20 years.
    """
    return position_at_year(target, mjd_to_jyear(mjd))


def position_at_year(target: Target, jyear: float) -> tuple[float, float]:
    dt = jyear - target.ref_epoch_yr
    ddec_deg = target.pmdec_masyr * dt / 3.6e6
    dec = target.dec + ddec_deg
    cos_dec = math.cos(math.radians(target.dec + ddec_deg / 2.0))
    dra_deg = target.pmra_masyr * dt / 3.6e6 / cos_dec
    return (target.ra + dra_deg) % 360.0, dec


def angular_sep_arcmin(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """True angular separation on the sphere (haversine, stable for small angles)."""
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    h = math.sin((d2 - d1) / 2) ** 2 + math.cos(d1) * math.cos(d2) * math.sin((r2 - r1) / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(h)))) * 60.0


def closest_point_on_track(
    target: Target, ra: float, dec: float, epoch_min: float, epoch_max: float
) -> tuple[float, float]:
    """(separation in arcmin, Julian year) of the point of the target's track nearest to (ra, dec).

    The track is the target's position under its catalog proper motion between `epoch_min` and
    `epoch_max`. Any catalog position of the target (2MASS ~1999, J2000 tables, AllWISE 2010, Gaia
    2016, the SPHEREx dates) lies on it, so a coordinate copied from any of them finds the field.
    """
    pm2 = target.pmra_masyr**2 + target.pmdec_masyr**2
    if pm2 == 0.0:
        year = min(max(target.ref_epoch_yr, epoch_min), epoch_max)
    else:
        # offsets of the query from the reference position on the tangent plane, in mas
        cos_d = math.cos(math.radians(target.dec))
        dra = ((ra - target.ra + 180.0) % 360.0 - 180.0) * cos_d * 3.6e6
        ddec = (dec - target.dec) * 3.6e6
        year = target.ref_epoch_yr + (dra * target.pmra_masyr + ddec * target.pmdec_masyr) / pm2
        year = min(max(year, epoch_min), epoch_max)
    ra_t, dec_t = position_at_year(target, year)
    return angular_sep_arcmin(ra, dec, ra_t, dec_t), year
