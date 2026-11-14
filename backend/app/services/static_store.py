"""Read the precomputed products of each field from disk (data/static/fields/<field_id>/)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from astropy.time import Time

from pipeline.targets import Target, load_targets, propagate


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
        out = []
        for t in self.targets.values():
            folder = self._field_dir(t.target_id)
            has_manifest = folder is not None and (folder / "manifest.json").is_file()
            out.append(
                {
                    "target_id": t.target_id,
                    "name": t.name,
                    "kind": t.kind,
                    "behavior": list(t.behavior),
                    "short_description": t.short_description,
                    "static_manifest_url": f"/static/fields/{t.target_id}/manifest.json" if has_manifest else None,
                }
            )
        return out

    def find_target_near(self, ra: float, dec: float, radius_arcmin: float) -> str | None:
        """Target whose current position is within `radius_arcmin` of (ra, dec).

        BR-FIELD-05: the catalog position (e.g. the 2010 coordinate in the challenge) only finds the
        target; the field itself is always centred on the propagated position.
        """
        now_mjd = float(Time.now().mjd)
        best, best_sep = None, radius_arcmin
        for t in self.targets.values():
            # current position first, then the catalog position (e.g. the statement's 2010 coordinates)
            for mjd in (now_mjd, None):
                tra, tdec = propagate(t, mjd) if mjd else (t.ra, t.dec)
                sep = _sep_arcmin(ra, dec, tra, tdec)
                if sep <= best_sep:
                    best, best_sep = t.target_id, sep
        return best


def _sep_arcmin(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    cos_sep = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_sep)))) * 60.0
