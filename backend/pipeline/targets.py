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
    dt = mjd_to_jyear(mjd) - target.ref_epoch_yr
    ddec_deg = target.pmdec_masyr * dt / 3.6e6
    dec = target.dec + ddec_deg
    cos_dec = math.cos(math.radians(target.dec + ddec_deg / 2.0))
    dra_deg = target.pmra_masyr * dt / 3.6e6 / cos_dec
    return (target.ra + dra_deg) % 360.0, dec
