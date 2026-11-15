"""Live fields (LIVE_FIELDS=true): built on request from the archive, cached, bounded in time."""

from __future__ import annotations

import time

import httpx
import pytest

from pipeline.build_field import cutout_read_size
from pipeline.read import read_cutout
from pipeline.synthetic import synthetic_exposures
from pipeline.targets import Target, propagate

FAR = {"ra": 10.004, "dec": 10.001, "fov_arcmin": 3}


@pytest.fixture(scope="module")
def synthetic_cutouts(tmp_path_factory):
    t = Target(target_id="sky", name="sky", kind="star", behavior=[], ra=10.0, dec=10.0)
    paths, _ = synthetic_exposures(t, tmp_path_factory.mktemp("live_fits"), seed=3)
    return [c for p in paths if (c := read_cutout(str(p), lambda mjd: propagate(t, mjd), cutout_read_size(31), False))]


@pytest.fixture()
def live_client(monkeypatch, tmp_path):
    from tests.conftest import _make_client

    monkeypatch.setenv("LIVE_FIELDS", "true")
    monkeypatch.setenv("LIVE_CACHE_DIR", str(tmp_path / "live"))
    monkeypatch.setenv("LIVE_TIMEOUT_S", "5")
    yield _make_client(monkeypatch)
    from app.deps import reset_caches

    reset_caches()


def _use_fetch(monkeypatch, fetch):
    monkeypatch.setattr("app.services.live.default_fetch", fetch)


def test_disabled_by_default(client):
    r = client.get("/api/field", params=FAR)
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_coverage"


def test_builds_a_field_for_any_position_and_caches_it(live_client, monkeypatch, synthetic_cutouts):
    calls = []

    def fetch(target, max_per):
        calls.append((target.ra, target.dec, max_per))
        return synthetic_cutouts

    _use_fetch(monkeypatch, fetch)
    r = live_client.get("/api/field", params=FAR)
    assert r.status_code == 200 and r.headers["x-field-match"] == "live"
    m = r.json()
    assert m["field_id"] == "live_10.00_10.00" and m["target_id"] is None
    assert calls == [(10.0, 10.0, 6)]  # rounded to 0.01 deg, at most 6 exposures per epoch and detector
    assert all(e["expected_position"] is None for e in m["epochs"])
    frame = m["epochs"][0]["frames"][0]
    assert frame["data_url"].startswith("/static/live/live_10.00_10.00/") and frame["data_url"].endswith(".bin")
    data = live_client.get(frame["data_url"])
    assert data.status_code == 200 and len(data.content) == 31 * 31 * 4
    # a nearby request (same 0.01 deg cell) is served from the cache
    again = live_client.get("/api/field", params={"ra": 10.001, "dec": 9.998})
    assert again.status_code == 200 and again.json() == m and len(calls) == 1
    # published targets still win over live fields
    assert live_client.get("/api/field", params={"ra": 133.75945, "dec": -7.24286}).headers["x-field-match"] == "center"


def test_irsa_unavailable_is_503_upstream_unavailable(live_client, monkeypatch):
    def fetch(target, max_per):
        request = httpx.Request("GET", "https://irsa.ipac.caltech.edu/SIA")
        raise httpx.HTTPStatusError("busy", request=request, response=httpx.Response(503, request=request))

    _use_fetch(monkeypatch, fetch)
    r = live_client.get("/api/field", params=FAR)
    assert r.status_code == 503 and r.json()["error"]["code"] == "upstream_unavailable"


def test_no_exposures_is_404_no_coverage_and_remembered(live_client, monkeypatch):
    calls = []

    def fetch(target, max_per):
        calls.append(1)
        return []

    _use_fetch(monkeypatch, fetch)
    for _ in range(2):
        r = live_client.get("/api/field", params=FAR)
        assert r.status_code == 404 and r.json()["error"]["code"] == "no_coverage"
    assert len(calls) == 1


def test_slow_build_answers_504_and_finishes_in_the_background(live_client, monkeypatch, synthetic_cutouts):
    from app.config import get_settings

    get_settings().live_timeout_s = 0.2

    def fetch(target, max_per):
        time.sleep(1.0)
        return synthetic_cutouts

    _use_fetch(monkeypatch, fetch)
    r = live_client.get("/api/field", params=FAR)
    assert r.status_code == 504 and r.json()["error"]["code"] == "live_field_timeout"
    get_settings().live_timeout_s = 10
    r = live_client.get("/api/field", params=FAR)  # joins the build already running
    assert r.status_code == 200 and r.json()["field_id"] == "live_10.00_10.00"
