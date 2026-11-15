"""Source measurement on the coadds (pipeline.sources)."""

from __future__ import annotations

import json
import shutil

import numpy as np

from pipeline.sources import Frame, Grid, build_sources, forced_fluxes, psf_image
from pipeline.targets import load_targets


def test_grid_round_trip_and_orientation():
    grid = Grid({"center": {"ra": 133.75945, "dec": -7.24286}, "pixscale_arcsec": 6.2, "nx": 31, "ny": 31})
    assert grid.to_xy(133.75945, -7.24286) == (15.0, 15.0)
    x, y = grid.to_xy(133.75945 + 6.2 / 3600 / np.cos(np.radians(-7.24286)), -7.24286 + 6.2 / 3600)
    assert abs(x - 14.0) < 1e-6 and abs(y - 14.0) < 1e-6  # east is left, north is up
    ra, dec = grid.to_sky(*grid.to_xy(133.7, -7.2))
    assert abs(ra - 133.7) < 1e-9 and abs(dec + 7.2) < 1e-9


def test_forced_photometry_separates_a_blend():
    """Two sources 1.4 px apart: joint PSF fitting recovers each flux (an aperture would sum them)."""
    rng = np.random.default_rng(0)
    pos = [(15.0, 15.0), (16.0, 14.0)]
    image = 50 * psf_image(*pos[0], 0.5, (31, 31)) + 120 * psf_image(*pos[1], 0.5, (31, 31))
    image += rng.normal(0, 0.05, image.shape)
    flux, err, _ = forced_fluxes(Frame(0, 5, image, 0.05), pos, 0.5)
    assert abs(flux[0] - 50) < 3 * err[0] + 0.5 and abs(flux[1] - 120) < 3 * err[1] + 0.5


def test_without_catalogs_the_target_is_still_a_row_and_nothing_claims_no_counterpart(tmp_path):
    """BR-CLS-06: no cross-match -> catalog not_checked, never uncatalogued; the target is always there."""
    src = "static/fields/rdra"
    dst = tmp_path / "rdra"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("sources.json", "catalogs.json"))
    doc = build_sources(dst, load_targets()["rdra"], None, {})
    assert doc["catalogs_checked"] is False
    target = next(r for r in doc["sources"] if r["is_target"])
    assert target["catalog"]["status"] == "known_typed"
    assert all(r["catalog"]["status"] in ("known_typed", "not_checked") for r in doc["sources"])
    json.dumps(doc)  # serialisable
