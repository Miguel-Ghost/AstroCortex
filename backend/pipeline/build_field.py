"""Build the flipbook products of one field and write manifest.json (contract 7.2 of the frontend guide).

Usage:
    # real data (IRSA SIA + S3), run offline, not on the Render free instance
    python -m pipeline.build_field --target wise0855

    # local FITS files (testing)
    python -m pipeline.build_field --target wise0855 --fits path/to/*.fits
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.time import Time

from . import DETECTORS, PIXSCALE_ARCSEC
from .coadd import coadd, protected_bits
from .epochs import group_epochs
from .grid import make_grid_wcs, reproject_cutout
from .read import Cutout, read_cutout
from .render import grid_to_png_xy, save_flags_png, save_float32, save_png, stretch_limits
from .targets import Target, jyear_to_mjd, load_targets, propagate

log = logging.getLogger("pipeline")
DEFAULT_OUT_ROOT = Path(__file__).resolve().parent.parent / "data" / "static" / "fields"


def cutout_read_size(size_px: int) -> int:
    """Read a larger window than the output grid so a rotated exposure still covers it."""
    n = int(math.ceil(size_px * 1.5))
    return n if n % 2 == 1 else n + 1


def build_field(
    target: Target,
    cutouts: list[Cutout],
    out_dir: Path,
    url_prefix: str,
    *,
    size_px: int = 31,
    data_release: str = "spherex_dr1",
    pipeline_commit: str = "dev",
    synthetic: bool = False,
    exclude_bits: int = 0,
    write_data: bool = True,
) -> dict:
    if not cutouts:
        raise ValueError(f"No cutouts for {target.target_id}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    mjds = np.array([c.mjd for c in cutouts])
    center_mjd = float(np.median(mjds))
    ra_c, dec_c = propagate(target, center_mjd)  # BR-FIELD-01: fixed centre for the whole field
    grid = make_grid_wcs(ra_c, dec_c, size_px, PIXSCALE_ARCSEC)
    aligned = [reproject_cutout(c, grid, size_px) for c in cutouts]

    groups = group_epochs(mjds)
    protected = 0
    for c in cutouts:
        protected |= protected_bits(c.flag_bits or {})
    frames: dict[tuple[int, int], tuple] = {}
    for e, members in enumerate(groups):
        by_detector: dict[int, list[int]] = defaultdict(list)
        for i in members:
            by_detector[cutouts[i].detector].append(i)
        for det, idx in by_detector.items():
            frames[(e, det)] = coadd(
                [aligned[i][0] for i in idx],
                [aligned[i][1] for i in idx],
                [aligned[i][2] for i in idx],
                exclude_bits=exclude_bits,
                protected=protected,
            )

    detectors = sorted({det for (_, det) in frames})
    # BR-FIELD-02: one stretch per detector for all epochs
    limits = {d: stretch_limits([f[0] for (_, dd), f in frames.items() if dd == d]) for d in detectors}

    epochs = []
    for e, members in enumerate(groups):
        mjd_e = float(np.mean(mjds[members]))
        ra_e, dec_e = propagate(target, mjd_e)
        gx, gy = grid.world_to_pixel(SkyCoord(ra_e * u.deg, dec_e * u.deg))
        px, py = grid_to_png_xy(float(gx), float(gy), size_px)
        frame_list = []
        for det in detectors:
            if (e, det) not in frames:
                continue  # BR-FIELD-04: an epoch may miss detectors; the gap is shown, never filled
            image, _variance, flags, n = frames[(e, det)]
            stem = f"e{e + 1}_d{det}"
            save_png(image, *limits[det], out_dir / f"{stem}.png")
            save_flags_png(flags, out_dir / f"{stem}_flags.png")
            data_url = None
            if write_data:
                save_float32(image, out_dir / f"{stem}.f32")
                data_url = f"{url_prefix}/{stem}.f32"
            frame_list.append(
                {
                    "detector": det,
                    "image_url": f"{url_prefix}/{stem}.png",
                    "data_url": data_url,
                    "flags_url": f"{url_prefix}/{stem}_flags.png",
                    "n_exposures": n,
                    "flagged_frac": round(float((flags != 0).mean()), 4),
                }
            )
        epochs.append(
            {
                "epoch_id": f"e{e + 1}",
                "mjd_avg": round(mjd_e, 4),
                "date_iso": Time(mjd_e, format="mjd").to_value("iso", subfmt="date"),
                "frames": frame_list,
                "expected_position": {
                    "ra": round(ra_e, 6),
                    "dec": round(dec_e, 6),
                    "x": round(px, 2),
                    "y": round(py, 2),
                },
            }
        )

    manifest = {
        "field_id": target.target_id,
        "target_id": target.target_id,
        "center": {"ra": round(ra_c, 6), "dec": round(dec_c, 6)},
        "center_mjd": round(center_mjd, 4),
        "fov_arcmin": round(size_px * PIXSCALE_ARCSEC / 60.0, 3),
        "pixscale_arcsec": PIXSCALE_ARCSEC,
        "nx": size_px,
        "ny": size_px,
        "orientation": "north_up_east_left",
        "data_release": data_release,
        "pipeline_commit": pipeline_commit,
        "synthetic": synthetic,  # BR-FIELD-03
        "flux_unit": "MJy/sr",
        "detectors": [
            {
                "detector": d,
                "lambda_min_um": DETECTORS[d][0],
                "lambda_max_um": DETECTORS[d][1],
                "stretch": {"type": "asinh", "vmin": limits[d][0], "vmax": limits[d][1]},
            }
            for d in detectors
        ],
        "epochs": epochs,
        "spectrum_url": None,
        "autotype_url": None,
        "lightcurve_url": None,
        "sources_url": f"/api/sources?field_id={target.target_id}",
        "catalogs_url": f"/api/catalogs?field_id={target.target_id}",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _detector_from_bandpass(name: str | None) -> int | None:
    match = re.search(r"(\d)", name or "")
    return int(match.group(1)) if match else None


def select_rows(rows: list[dict], max_per_epoch_detector: int) -> list[dict]:
    """Cap the number of exposures per epoch and detector before reading (BR-PIPE-02: never global)."""
    if not rows:
        return []
    mjds = [((r.get("t_min") or 0) + (r.get("t_max") or 0)) / 2 for r in rows]
    kept: list[dict] = []
    for members in group_epochs(mjds):
        counts: dict[int | None, int] = defaultdict(int)
        for i in members:
            det = _detector_from_bandpass(rows[i].get("energy_bandpassname"))
            if counts[det] < max_per_epoch_detector:
                counts[det] += 1
                kept.append(rows[i])
    return kept


def fetch_cutouts(target: Target, size_px: int, max_per_epoch_detector: int = 6, workers: int = 4) -> list[Cutout]:
    """Query IRSA and read the cutouts from S3 (4 parallel reads, as agreed in the plan)."""
    from .query import exposures_for

    ra, dec = propagate(target, jyear_to_mjd(2026.0))
    rows = select_rows(exposures_for(ra, dec, radius_deg=0.05), max_per_epoch_detector)
    read_size = cutout_read_size(size_px)

    def work(row: dict) -> Cutout | None:
        try:
            return read_cutout(row["s3_url"], lambda mjd: propagate(target, mjd), read_size, remote=True)
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the field
            log.warning("skip %s: %s", row.get("s3_url"), exc)
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return [c for c in pool.map(work, rows) if c is not None]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--size", type=int, default=31)
    parser.add_argument("--fits", nargs="*", help="local FITS files instead of IRSA/S3")
    parser.add_argument("--max-per-epoch-detector", type=int, default=6)
    parser.add_argument("--data-release", default="spherex_dr1")
    parser.add_argument("--commit", default="dev")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    target = load_targets()[args.target]
    if args.fits:
        read_size = cutout_read_size(args.size)
        cutouts = [
            c for f in args.fits if (c := read_cutout(f, lambda mjd: propagate(target, mjd), read_size, remote=False))
        ]
    else:
        cutouts = fetch_cutouts(target, args.size, args.max_per_epoch_detector)
    log.info("%s: %d cutouts", target.target_id, len(cutouts))
    manifest = build_field(
        target,
        cutouts,
        args.out_root / target.target_id,
        f"/static/fields/{target.target_id}",
        size_px=args.size,
        data_release=args.data_release,
        pipeline_commit=args.commit,
    )
    log.info("%s: %d epochs written to %s", target.target_id, len(manifest["epochs"]), args.out_root / target.target_id)


if __name__ == "__main__":
    main()
