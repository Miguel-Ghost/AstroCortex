"""Generate demo data for the 5 targets from synthetic exposures (all files say synthetic: true).

It runs the real pipeline code on fake SPHEREx-like files, so the frontend gets data with the
exact production format before the real fields exist. Replace each folder with real output
from `python -m pipeline.build_field --target <id>` as soon as it is available.

    python -m scripts.make_mock_static            # all targets
    python -m scripts.make_mock_static wise0855   # some targets
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
import zlib
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord

from pipeline import PIXSCALE_ARCSEC
from pipeline.build_field import DEFAULT_OUT_ROOT, build_field, cutout_read_size
from pipeline.grid import make_grid_wcs
from pipeline.read import read_cutout
from pipeline.render import grid_to_png_xy
from pipeline.synthetic import synthetic_exposures
from pipeline.targets import Target, load_targets, propagate

MOCK_METHANE = {"wise0855": 40.0, "epsindib": 6.0}  # illustrative values for demo data only


def _pixel(manifest: dict, ra: float, dec: float) -> tuple[float, float]:
    grid = make_grid_wcs(manifest["center"]["ra"], manifest["center"]["dec"], manifest["nx"], PIXSCALE_ARCSEC)
    gx, gy = grid.world_to_pixel(SkyCoord(ra * u.deg, dec * u.deg))
    return grid_to_png_xy(float(gx), float(gy), manifest["ny"])


def build_tour(t: Target, manifest: dict, motion_px: float, source_id: str) -> dict:
    first, last = manifest["epochs"][0], manifest["epochs"][-1]
    detector = 6 if t.kind == "cold_brown_dwarf" else 2
    steps = [
        {
            "say": f"This is {t.name}. {t.short_description}",
            "actions": [
                {"type": "select_target", "target_id": t.target_id},
                {"type": "set_detector", "detector": detector},
            ],
        }
    ]
    if "moves" in t.behavior:
        pos = last["expected_position"]
        steps.append(
            {
                "say": f"Compare the first and last dates: it shifts about {motion_px:.1f} pixels.",
                "actions": [
                    {"type": "blink", "epoch_a": first["epoch_id"], "epoch_b": last["epoch_id"]},
                    {"type": "highlight", "ra": pos["ra"], "dec": pos["dec"], "label": t.name},
                ],
            }
        )
    if t.kind == "cold_brown_dwarf":
        steps.append(
            {
                "say": "In the bluer detectors it almost disappears; it is brightest near 4-5 microns.",
                "actions": [{"type": "show_detector_grid"}],
            }
        )
    if "varies" in t.behavior:
        steps.append(
            {
                "say": "Play the dates: its brightness changes from one visit to the next.",
                "actions": [{"type": "play_flipbook", "fps": 2}],
            }
        )
    steps.append(
        {
            "say": "The classification panel lists every source in this field, candidates first.",
            "actions": [
                {"type": "select_source", "source_id": source_id},
                {"type": "open_tab", "tab": "classification"},
            ],
        }
    )
    return {
        "reply": f"Here is a short tour of {t.name}.",
        "steps": steps,
        "sources_used": [f"/api/field?target_id={t.target_id}", f"/api/sources?field_id={t.target_id}"],
    }


def build_target(t: Target, out_root: Path, workdir: Path, size_px: int = 31) -> dict:
    seed = zlib.crc32(t.target_id.encode())
    rng = np.random.default_rng(seed)
    paths, stars = synthetic_exposures(t, Path(workdir) / t.target_id, seed=seed)
    read_size = cutout_read_size(size_px)
    cutouts = [c for p in paths if (c := read_cutout(str(p), lambda mjd: propagate(t, mjd), read_size, remote=False))]
    out_dir = Path(out_root) / t.target_id
    manifest = build_field(
        t,
        cutouts,
        out_dir,
        f"/static/fields/{t.target_id}",
        size_px=size_px,
        data_release="synthetic",
        pipeline_commit="mock",
        synthetic=True,
    )

    p0, p1 = manifest["epochs"][0]["expected_position"], manifest["epochs"][-1]["expected_position"]
    motion_px = math.hypot(p1["x"] - p0["x"], p1["y"] - p0["y"])
    flagged = float(np.mean([f["flagged_frac"] for e in manifest["epochs"] for f in e["frames"]]))
    ra_t, dec_t = manifest["center"]["ra"], manifest["center"]["dec"]
    x, y = _pixel(manifest, ra_t, dec_t)
    target_source = {
        "source_id": f"{t.target_id}_s000",
        "ra": ra_t,
        "dec": dec_t,
        "x": round(x, 2),
        "y": round(y, 2),
        "evidence": {
            "motion_px": round(motion_px, 2),
            "pm_mas_yr": {"pmra": t.pmra_masyr, "pmdec": t.pmdec_masyr},
            "methane_index": MOCK_METHANE.get(t.target_id, 1.0),
            "in_gaia": t.target_id != "wise0855",
            "in_catwise": True,
            "jpl_match": None,
            "extended": False,
            "variable": "varies" in t.behavior,
            "flagged_frac": round(flagged, 4),
        },
        "obs_ids": [],
        "epoch_mjd": manifest["center_mjd"],
    }
    sources, gaia, wise = [target_source], [], []
    if target_source["evidence"]["in_gaia"]:
        gaia.append(
            {
                "source_id": f"mock-{t.target_id}",
                "ra": ra_t,
                "dec": dec_t,
                "g_mag": None,
                "pmra": t.pmra_masyr,
                "pmdec": t.pmdec_masyr,
            }
        )
    wise.append({"name": f"mock-{t.target_id}", "ra": ra_t, "dec": dec_t, "w1": None, "w2": None})
    for i, (ra, dec, _flux) in enumerate(stars, start=1):
        x, y = _pixel(manifest, ra, dec)
        pm = {"pmra": round(float(rng.normal(0, 8)), 1), "pmdec": round(float(rng.normal(0, 8)), 1)}
        sources.append(
            {
                "source_id": f"{t.target_id}_s{i:03d}",
                "ra": round(ra, 6),
                "dec": round(dec, 6),
                "x": round(x, 2),
                "y": round(y, 2),
                "evidence": {
                    "motion_px": 0.0,
                    "pm_mas_yr": pm,
                    "methane_index": round(float(rng.uniform(0.8, 1.2)), 2),
                    "in_gaia": True,
                    "in_catwise": True,
                    "jpl_match": None,
                    "extended": False,
                    "variable": False,
                    "flagged_frac": round(flagged, 4),
                },
                "obs_ids": [],
                "epoch_mjd": manifest["center_mjd"],
            }
        )
        gaia.append(
            {
                "source_id": f"mock-{t.target_id}-{i}",
                "ra": round(ra, 6),
                "dec": round(dec, 6),
                "g_mag": round(float(rng.uniform(13, 17)), 2),
                **pm,
            }
        )
        wise.append(
            {
                "name": f"mock-{t.target_id}-{i}",
                "ra": round(ra, 6),
                "dec": round(dec, 6),
                "w1": round(float(rng.uniform(11, 14)), 2),
                "w2": round(float(rng.uniform(11, 14)), 2),
            }
        )

    (out_dir / "sources.json").write_text(json.dumps({"synthetic": True, "sources": sources}, indent=2))
    (out_dir / "catalogs.json").write_text(
        json.dumps({"synthetic": True, "epoch_mjd": manifest["center_mjd"], "gaia": gaia, "wise": wise}, indent=2)
    )
    (out_dir / "agent_tour.json").write_text(
        json.dumps(build_tour(t, manifest, motion_px, target_source["source_id"]), indent=2)
    )
    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", help="target ids (default: all)")
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    args = parser.parse_args(argv)
    targets = load_targets()
    ids = args.targets or list(targets)
    workdir = Path(tempfile.mkdtemp(prefix="spherex-mock-"))
    try:
        for tid in ids:
            manifest = build_target(targets[tid], args.out_root, workdir)
            print(f"{tid}: {len(manifest['epochs'])} epochs -> {args.out_root / tid}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
