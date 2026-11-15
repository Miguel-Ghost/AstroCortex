"""Read the precomputed products of each field from disk (data/static/fields/<field_id>/)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pipeline.targets import Target, load_targets


class StaticStore:
    def __init__(self, fields_dir: Path, targets_file: Path):
        self.fields_dir = Path(fields_dir)
        self.targets: dict[str, Target] = load_targets(targets_file)

    def _field_dir(self, field_id: str) -> Path | None:
        # field ids are plain names; refuse anything that could escape the folder
        if not field_id or not field_id.replace("_", "").replace("-", "").isalnum():
            return None
        path = self.fields_dir / field_id
        return path if path.is_dir() else None

    def read_json(self, field_id: str, name: str) -> Any | None:
        folder = self._field_dir(field_id)
        if folder is None or not (folder / name).is_file():
            return None
        return json.loads((folder / name).read_text(encoding="utf-8"))

    def manifest(self, field_id: str) -> dict | None:
        return self.read_json(field_id, "manifest.json")

    def list_targets(self) -> list[dict]:
        return [
            {
                "target_id": t.target_id,
                "name": t.name,
                "short": t.short_description,
                "motion_arcsec_yr": t.motion_arcsec_yr,
                "default_detector": t.default_detector,
                "aliases": list(t.aliases),
                "approx_center": dict(t.approx_center),
                "static_manifest_url": f"/static/fields/{t.target_id}/manifest.json",
            }
            for t in self.targets.values()
        ]

    def has_manifest(self, field_id: str) -> bool:
        folder = self._field_dir(field_id)
        return folder is not None and (folder / "manifest.json").is_file()

    def find_target_near(self, ra: float, dec: float, radius_arcmin: float) -> str | None:
        """Target whose published field centre is less than `radius_arcmin` from (ra, dec).

        BR-FIELD-05: the separation is the true angular distance on the sphere, and the reference is
        the centre of the published field (the target propagated to the epochs), never the
        challenge's 2010 coordinate.
        """
        best, best_sep = None, radius_arcmin
        for t in self.targets.values():
            center = t.approx_center
            if not center:
                continue
            sep = _sep_arcmin(ra, dec, float(center["ra"]), float(center["dec"]))
            if sep < best_sep:
                best, best_sep = t.target_id, sep
        return best


def _sep_arcmin(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    cos_sep = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_sep)))) * 60.0
