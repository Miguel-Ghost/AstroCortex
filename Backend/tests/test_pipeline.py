from __future__ import annotations

import math

import numpy as np
import pytest
from astropy.wcs import WCS, Sip
from PIL import Image

from app.schemas import FieldManifest
from pipeline.build_field import build_field, cutout_read_size, select_rows
from pipeline.coadd import coadd
from pipeline.epochs import group_epochs
from pipeline.query import s3_key_from_cloud_access
from pipeline.read import read_cutout, read_section, shift_wcs
from pipeline.synthetic import synthetic_exposures
from pipeline.targets import jyear_to_mjd, load_targets, propagate

TARGETS = load_targets()


def test_propagate_at_reference_epoch_returns_catalog_position():
    t = TARGETS["wise0855"]
    ra, dec = propagate(t, jyear_to_mjd(t.ref_epoch_yr))
    assert ra == pytest.approx(t.ra, abs=1e-9) and dec == pytest.approx(t.dec, abs=1e-9)


def test_propagate_displacement_matches_proper_motion():
    """BR-FIELD-05: positions are propagated with the proper motion."""
    t = TARGETS["wise0855"]
    ra, dec = propagate(t, jyear_to_mjd(t.ref_epoch_yr + 10))
    dra = (ra - t.ra) * math.cos(math.radians((dec + t.dec) / 2)) * 3600
    ddec = (dec - t.dec) * 3600
    assert math.hypot(dra, ddec) == pytest.approx(t.pm_total_masyr * 10 / 1000, rel=0.005)
    assert dra < 0  # WISE 0855 moves west


def test_read_section_pads_outside_the_array():
    full = np.arange(100, dtype=float).reshape(10, 10)
    window, origin = read_section(full, full.shape, 0.0, 0.0, 5, np.nan)
    assert origin == (-2, -2)
    assert np.isnan(window[0, 0]) and window[2, 2] == full[0, 0] and window[4, 4] == full[2, 2]


def test_shift_wcs_keeps_sky_positions_with_sip():
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN-SIP", "DEC--TAN-SIP"]
    w.wcs.crval = [133.76, -7.24]
    w.wcs.crpix = [1020.0, 1020.0]
    w.wcs.cdelt = [-6.2 / 3600, 6.2 / 3600]
    a = np.zeros((3, 3))
    a[2, 0] = 1e-6
    b = np.zeros((3, 3))
    b[0, 2] = -1e-6
    w.sip = Sip(a, b, None, None, w.wcs.crpix)
    shifted = shift_wcs(w, -7, 300)
    for x, y in [(10.0, 20.0), (1500.0, 900.0)]:
        sky_full = w.all_pix2world([[x, y]], 0)[0]
        sky_cut = shifted.all_pix2world([[x + 7, y - 300]], 0)[0]
        assert np.allclose(sky_full, sky_cut, atol=1e-10)


def test_group_epochs_splits_on_gaps_and_long_spans():
    assert group_epochs([1.0, 1.5, 200.0, 2.0, 400.0]) == [[0, 1, 3], [2], [4]]
    continuous = np.arange(0, 70, 1.0)  # near the poles: daily visits for 70 days
    assert len(group_epochs(continuous, gap_days=10, max_span_days=30)) == 3


def test_source_and_outlier_flags_cannot_be_excluded_from_a_coadd():
    """BR-PIPE-01."""
    from astropy.io import fits

    from pipeline.coadd import protected_bits
    from pipeline.read import flag_bits_from_header

    header = fits.Header()
    header["MSKN0"] = "TRANSIENT"
    header["MSKN5"] = "SOURCE"
    header["MSKN7"] = "OUTLIER"
    protected = protected_bits(flag_bits_from_header(header))
    assert protected == (1 << 5) | (1 << 7)
    img = [np.ones((2, 2)), np.ones((2, 2))]
    var = [np.ones((2, 2)), np.ones((2, 2))]
    flg = [np.zeros((2, 2), int), np.zeros((2, 2), int)]
    coadd(img, var, flg, exclude_bits=1, protected=protected)  # TRANSIENT may be excluded
    with pytest.raises(ValueError, match="BR-PIPE-01"):
        coadd(img, var, flg, exclude_bits=1 << 5, protected=protected)


def test_coadd_is_inverse_variance_weighted_and_ors_flags():
    img, var, flags, n = coadd(
        [np.full((2, 2), 1.0), np.full((2, 2), 4.0)],
        [np.full((2, 2), 1.0), np.full((2, 2), 4.0)],
        [np.zeros((2, 2), int), np.array([[0, 2], [0, 0]])],
    )
    assert n == 2
    assert img[0, 0] == pytest.approx((1 * 1 + 4 * 0.25) / 1.25)
    assert var[0, 0] == pytest.approx(1 / 1.25)
    assert flags[0, 1] == 2 and flags[0, 0] == 0


def test_select_rows_caps_per_epoch_and_detector():
    """BR-PIPE-02: the cap applies per epoch and detector, not globally."""
    rows = [{"t_min": 100 + i * 0.1, "t_max": 100 + i * 0.1, "energy_bandpassname": "SPHEREx-D1"} for i in range(10)]
    rows += [{"t_min": 300.0, "t_max": 300.0, "energy_bandpassname": "SPHEREx-D5"}]
    kept = select_rows(rows, max_per_epoch_detector=3)
    assert len(kept) == 4


def test_qr2_keys_are_never_read(monkeypatch):
    """BR-PIPE-03."""
    from pipeline import query

    rows = [
        {"cloud_access": '{"aws": {"key": "qr2/level2/a.fits"}}'},
        {"cloud_access": '{"aws": {"key": "qr/level2/b.fits"}}'},
    ]
    monkeypatch.setattr(query, "sia_query", lambda *a, **k: rows)
    keys = [r["s3_url"].rsplit("/", 1)[-1] for r in query.exposures_for(1.0, 2.0, collections=("x",))]
    assert keys == ["b.fits"]


def test_s3_key_from_cloud_access():
    blob = '{"aws": {"bucket_name": "nasa-irsa-spherex", "key": "qr/level2/x.fits", "region": "us-east-1"}}'
    assert s3_key_from_cloud_access(blob) == "qr/level2/x.fits"


def _centroid(arr: np.ndarray, x: float, y: float, radius: float = 3.0) -> tuple[float, float]:
    yy, xx = np.mgrid[0 : arr.shape[0], 0 : arr.shape[1]]
    near = np.hypot(xx - x, yy - y) < radius
    iy, ix = np.unravel_index(np.argmax(np.where(near, np.nan_to_num(arr, nan=-np.inf), -np.inf)), arr.shape)
    w = np.where(np.hypot(xx - ix, yy - iy) <= 1.5, np.clip(np.nan_to_num(arr), 0, None), 0.0)
    return float((w * xx).sum() / w.sum()), float((w * yy).sum() / w.sum())


@pytest.fixture(scope="module")
def built_field(tmp_path_factory):
    t = TARGETS["wise0855"]
    tmp = tmp_path_factory.mktemp("field")
    paths, stars = synthetic_exposures(t, tmp / "fits", seed=7)
    cutouts = [
        c
        for p in paths
        if (c := read_cutout(str(p), lambda mjd: propagate(t, mjd), cutout_read_size(31), remote=False))
    ]
    manifest = build_field(t, cutouts, tmp / "out", "/static/fields/wise0855", synthetic=True)
    return t, tmp / "out", manifest, stars


def _frame(out_dir, manifest, epoch_index, detector):
    epoch = manifest["epochs"][epoch_index]
    frame = next(f for f in epoch["frames"] if f["detector"] == detector)
    name = frame["data_url"].rsplit("/", 1)[-1]
    return np.fromfile(out_dir / name, dtype="<f4").reshape(manifest["ny"], manifest["nx"]), epoch


def test_manifest_follows_the_contract(built_field):
    """BR-FIELD-03: a field built from synthetic exposures says so."""
    _, out_dir, manifest, _ = built_field
    FieldManifest.model_validate(manifest)
    assert manifest["synthetic"] is True
    assert len(manifest["epochs"]) == 3
    assert all(len(e["frames"]) == 6 for e in manifest["epochs"])
    png = Image.open(out_dir / "e1_d5.png")
    assert png.size == (31, 31) and png.mode == "LA"


def test_target_sits_on_the_crosshair_in_every_epoch(built_field):
    _, out_dir, manifest, _ = built_field
    for i in range(3):
        arr, epoch = _frame(out_dir, manifest, i, detector=5)
        pos = epoch["expected_position"]
        cx, cy = _centroid(arr, pos["x"], pos["y"])
        assert math.hypot(cx - pos["x"], cy - pos["y"]) < 0.4


def test_target_moves_west_and_field_stars_stay_put(built_field):
    """BR-FIELD-01: fixed centre, so stars stay put and only the moving target shifts."""
    from pipeline import PIXSCALE_ARCSEC
    from pipeline.grid import make_grid_wcs
    from pipeline.render import grid_to_png_xy

    _, out_dir, manifest, stars = built_field
    first, last = manifest["epochs"][0]["expected_position"], manifest["epochs"][-1]["expected_position"]
    assert last["x"] > first["x"]  # east-left orientation: moving west = moving right
    grid = make_grid_wcs(manifest["center"]["ra"], manifest["center"]["dec"], 31, PIXSCALE_ARCSEC)
    ra, dec, _ = stars[0]
    sx, sy = grid_to_png_xy(*map(float, grid.world_to_pixel_values(ra, dec)), 31)
    positions = [_centroid(_frame(out_dir, manifest, i, detector=2)[0], sx, sy) for i in range(3)]
    spread = max(math.hypot(p[0] - positions[0][0], p[1] - positions[0][1]) for p in positions)
    assert spread < 0.3


def test_cold_brown_dwarf_is_faint_in_blue_and_bright_in_red(built_field):
    _, out_dir, manifest, _ = built_field
    arr_blue, epoch = _frame(out_dir, manifest, 1, detector=1)
    arr_red, _ = _frame(out_dir, manifest, 1, detector=5)
    pos = epoch["expected_position"]
    ix, iy = int(round(pos["x"])), int(round(pos["y"]))
    assert arr_red[iy, ix] > 10 * arr_blue[iy, ix]


def test_one_stretch_per_detector_for_all_epochs(built_field):
    """BR-FIELD-02."""
    from pipeline.render import stretch_limits

    _, out_dir, manifest, _ = built_field
    for det in manifest["detectors"]:
        frames = [_frame(out_dir, manifest, i, det["detector"])[0] for i in range(len(manifest["epochs"]))]
        frames = [np.flipud(f) for f in frames]  # back to grid orientation (stretch is orientation-free anyway)
        vmin, vmax = stretch_limits(frames)
        assert det["stretch"]["vmin"] == pytest.approx(vmin) and det["stretch"]["vmax"] == pytest.approx(vmax)


def test_missing_detector_is_a_gap_not_filled(tmp_path):
    """BR-FIELD-04."""
    t = TARGETS["rdra"]
    paths, _ = synthetic_exposures(t, tmp_path / "fits", detectors=(1, 2, 3), per_epoch=1, seed=3)
    cutouts = [
        c
        for p in paths
        if (c := read_cutout(str(p), lambda mjd: propagate(t, mjd), cutout_read_size(31), remote=False))
        and not (c.detector == 3 and 61000 < c.mjd < 61010)  # drop detector 3 of the 2nd epoch
    ]
    manifest = build_field(t, cutouts, tmp_path / "out", "/static/fields/rdra", synthetic=True)
    dets = [[f["detector"] for f in e["frames"]] for e in manifest["epochs"]]
    assert dets == [[1, 2, 3], [1, 2], [1, 2, 3]]
