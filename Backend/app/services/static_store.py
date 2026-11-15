"""The published fields on disk (static/fields/<folder>/) and how requests find them.

Every request names a field in its own way: the frontend sends the manifest's `field_id`
(`f_wise0855`), the agent and the URL send a `target_id` (`wise0855`), people type a name
(`WISE 0855`). All of them resolve through one index built from the manifests, so no route builds
a path from user input and no route disagrees with another about what a field is called.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.targets import Target, angular_sep_arcmin, closest_point_on_track, load_targets


@dataclass(frozen=True)
class FieldRef:
    folder: str  # directory under fields_dir
    field_id: str  # canonical id, the manifest's field_id (e.g. "f_wise0855")
    target_id: str | None


@dataclass(frozen=True)
class FieldMatch:
    target_id: str
    by: str  # "center" | "track" | "target"
    epoch: float | None  # Julian year of the nearest point of the track (by == "track")
    offset_arcmin: float | None  # distance from the query to the field centre


def norm_key(value: str) -> str:
    return " ".join(str(value).lower().replace("\u2019", "'").replace("_", " ").split())


class StaticStore:
    def __init__(self, fields_dir: Path, targets_file: Path):
        self.fields_dir = Path(fields_dir)
        self.targets: dict[str, Target] = load_targets(targets_file)
        self._cache: dict[tuple[str, str], Any] = {}
        self._index: dict[str, FieldRef] = {}
        self._build_index()

    # -- index --------------------------------------------------------------------------------
    def _build_index(self) -> None:
        index: dict[str, FieldRef] = {}
        if self.fields_dir.is_dir():
            for folder in sorted(p for p in self.fields_dir.iterdir() if (p / "manifest.json").is_file()):
                try:
                    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue  # a broken manifest is not served; /health reports the count
                target_id = manifest.get("target_id") or (folder.name if folder.name in self.targets else None)
                ref = FieldRef(folder.name, str(manifest.get("field_id") or f"f_{folder.name}"), target_id)
                keys = [folder.name, f"f_{folder.name}", ref.field_id]
                if target_id:
                    keys.append(target_id)
                    target = self.targets.get(target_id)
                    if target:
                        keys += [target.name, *target.aliases]
                for key in keys:
                    index.setdefault(norm_key(key), ref)
        self._index = index

    def resolve(self, key: str | None) -> FieldRef | None:
        """The field named by a field_id, target_id, folder, target name or alias."""
        if not key:
            return None
        ref = self._index.get(norm_key(key))
        if ref is None:  # a field published after startup (live fields) is picked up on first use
            self._build_index()
            ref = self._index.get(norm_key(key))
        return ref

    def fields(self) -> list[FieldRef]:
        return sorted(set(self._index.values()), key=lambda r: r.folder)

    # -- files --------------------------------------------------------------------------------
    def read_json(self, field_key: str | None, name: str) -> Any | None:
        ref = self.resolve(field_key)
        if ref is None:
            return None
        cache_key = (ref.folder, name)
        if cache_key not in self._cache:
            path = self.fields_dir / ref.folder / name
            if not path.is_file():
                return None
            self._cache[cache_key] = json.loads(path.read_text(encoding="utf-8"))
        return self._cache[cache_key]

    def manifest(self, field_key: str | None) -> dict | None:
        return self.read_json(field_key, "manifest.json")

    def has_manifest(self, field_key: str | None) -> bool:
        return self.resolve(field_key) is not None

    # -- targets ------------------------------------------------------------------------------
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

    def locate(
        self, ra: float, dec: float, radius_arcmin: float, epoch_min: float = 1990.0, epoch_max: float = 2030.0
    ) -> FieldMatch | None:
        """The published field for (ra, dec). BR-FIELD-05.

        1. within `radius_arcmin` of a field centre (the target at the SPHEREx dates), else
        2. within `radius_arcmin` of the target's proper-motion track between epoch_min and
           epoch_max, so the challenge's 2010 coordinate of WISE 0855 or a J2000 position of
           Barnard's Star still opens the field where the star is now.
        Separations are true angular distances on the sphere. The nearest match wins.
        """
        published = [t for t in self.targets.values() if t.approx_center and self.has_manifest(t.target_id)]

        def offset(t: Target) -> float:
            return angular_sep_arcmin(ra, dec, float(t.approx_center["ra"]), float(t.approx_center["dec"]))

        centre = [(offset(t), t) for t in published]
        centre = [c for c in centre if c[0] < radius_arcmin]
        if centre:
            sep, t = min(centre, key=lambda c: c[0])
            return FieldMatch(t.target_id, "center", None, sep)
        track = [(*closest_point_on_track(t, ra, dec, epoch_min, epoch_max), t) for t in published]
        track = [c for c in track if c[0] < radius_arcmin]
        if track:
            _, year, t = min(track, key=lambda c: c[0])
            return FieldMatch(t.target_id, "track", year, offset(t))
        return None

    def find_target_near(self, ra: float, dec: float, radius_arcmin: float) -> str | None:
        match = self.locate(ra, dec, radius_arcmin)
        return match.target_id if match else None
