from __future__ import annotations

import pytest

from app.schemas import AgentResponse, CatalogsResponse, SourcesResponse, Target

WISE = {"ra": 133.75945, "dec": -7.24286, "fov_arcmin": 3}

# --- real fields (what Render serves) --------------------------------------------------------


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["classifier_method"] == "model"
    assert body["static_fields"] == 5
    assert body["checks"] == {"classifier": True, "static_fields": True, "marks": True}


def test_targets_lists_the_five_targets_with_their_catalogue_fields(client):
    targets = [Target.model_validate(t) for t in client.get("/api/targets").json()]
    assert [t.target_id for t in targets] == ["barnard", "epsindib", "wise0855", "rwaur", "rdra"]
    wise = targets[2]
    assert (wise.name, wise.motion_arcsec_yr, wise.default_detector) == ("WISE 0855-0714", 8.1, 5)
    assert (wise.approx_center.ra, wise.approx_center.dec) == (133.75945, -7.24286)
    assert wise.static_manifest_url == "/static/fields/wise0855/manifest.json"
    assert targets[0].name == "Barnard's Star" and targets[3].motion_arcsec_yr == 0


def test_field_returns_the_manifest_unchanged(client):
    r = client.get("/api/field", params=WISE)
    assert r.status_code == 200
    on_disk = client.get("/static/fields/wise0855/manifest.json").json()
    assert r.json() == on_disk  # same field names and values, nothing re-serialised
    assert r.json()["target_id"] == "wise0855" and len(r.json()["epochs"]) == 3
    assert r.headers["x-field-match"] == "center" and r.headers["x-target-id"] == "wise0855"


def test_field_ignores_fov_and_uses_true_angular_separation(client):
    """BR-FIELD-05: within 1 arcmin of the published centre, measured on the sphere."""
    # R Draconis is at dec +66.75: 0.03 deg of RA there is only ~0.71 arcmin on the sky -> covered
    near = client.get("/api/field", params={"ra": 248.16723 + 0.03, "dec": 66.75502, "fov_arcmin": 99})
    assert near.status_code == 200 and near.json()["target_id"] == "rdra"
    # 0.03 deg north of WISE 0855 is 1.8 arcmin off the centre and off its (east-west) track -> not covered
    far = client.get("/api/field", params={"ra": 133.75945, "dec": -7.24286 + 0.03})
    assert far.status_code == 404


def test_catalog_coordinates_of_any_epoch_open_the_field_where_the_target_is_now(client):
    """BR-FIELD-05: the challenge's 2010 coordinate of WISE 0855 and J2000 positions find the field."""
    cases = {
        "wise0855": (133.79513, -7.24515, 2010.5),  # challenge statement (AllWISE epoch)
        "barnard": (269.452071, 4.693364, 2000.0),  # SIMBAD J2000
        "epsindib": (331.04383, -56.78269, 2000.0),  # SIMBAD J2000
    }
    for target_id, (ra, dec, year) in cases.items():
        r = client.get("/api/field", params={"ra": ra, "dec": dec, "fov_arcmin": 3})
        assert r.status_code == 200 and r.json()["target_id"] == target_id, target_id
        assert r.headers["x-field-match"] == "track" and r.headers["x-target-id"] == target_id
        assert abs(float(r.headers["x-field-match-epoch"]) - year) < 1.0
        assert float(r.headers["x-field-offset-arcmin"]) > 1.5  # the target has moved since


def test_lookup_headers_are_exposed_to_the_browser(client):
    r = client.get("/api/field", params={"ra": 133.79513, "dec": -7.24515}, headers={"Origin": "http://localhost:5173"})
    exposed = r.headers["access-control-expose-headers"]
    for header in ("X-Field-Match", "X-Field-Match-Epoch", "X-Field-Offset-Arcmin", "X-Target-Id"):
        assert header in exposed


def test_field_ids_resolve_from_any_name(client):
    """BR-FIELD-06: field_id, target_id and aliases all name the same field."""
    for name in ("wise0855", "f_wise0855", "WISE 0855", "WISE J085510.83-071442.5"):
        r = client.get("/api/field", params={"target_id": name})
        assert r.status_code == 200 and r.json()["field_id"] == "wise0855", name
        assert client.get("/api/sources", params={"field_id": name}).json()["field_id"] == "wise0855"
    r = client.get("/api/sources", params={"field_id": "../wise0855"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "field_not_found"


def test_no_coverage_uses_the_exact_error_body(client):
    """BR-ERR-01."""
    r = client.get("/api/field", params={"ra": 10, "dec": 10, "fov_arcmin": 3})
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "no_coverage", "message": "No SPHEREx images cover this position yet."}}


def test_invalid_parameters_are_400_bad_request(client):
    """BR-ERR-01: every validation error is reported in details."""
    for params in ({"ra": 999, "dec": 0}, {"ra": "abc", "dec": 0}, {"ra": 10}, {"ra": 10, "dec": 0, "fov_arcmin": -1}):
        r = client.get("/api/field", params=params)
        assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request", params
    body = client.get("/api/field", params={"ra": 999, "dec": -100}).json()["error"]
    assert {tuple(e["loc"]) for e in body["details"]["errors"]} == {("query", "ra"), ("query", "dec")}


def test_static_files_types_sizes_and_cache(client):
    data = client.get("/static/fields/wise0855/e1_d5.bin")
    assert data.status_code == 200 and len(data.content) == 3844
    assert data.headers["content-type"] == "application/octet-stream"
    assert data.headers["cache-control"] == "public, max-age=3600"
    png = client.get("/static/fields/wise0855/e1_d5.png")
    assert png.headers["content-type"] == "image/png" and png.headers["cache-control"] == "public, max-age=3600"
    manifest = client.get("/static/fields/wise0855/manifest.json")
    assert manifest.headers["content-type"].startswith("application/json")


def test_every_frame_in_every_manifest_exists(client):
    for target in client.get("/api/targets").json():
        manifest = client.get(target["static_manifest_url"]).json()
        for epoch in manifest["epochs"]:
            for frame in epoch["frames"]:
                for key in ("image_url", "data_url", "flags_url"):
                    assert client.get(frame[key]).status_code == 200, frame[key]


def test_cors_allows_the_frontend_origin(client):
    r = client.get("/api/targets", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_origins_pasted_with_a_trailing_slash_still_match(monkeypatch):
    from tests.conftest import _make_client

    monkeypatch.setenv("CORS_ORIGINS", "https://astrocortex.example.org/, http://localhost:5173")
    monkeypatch.setenv("CORS_ORIGIN_REGEX", "")
    client = _make_client(monkeypatch)
    r = client.get("/api/targets", headers={"Origin": "https://astrocortex.example.org"})
    assert r.headers.get("access-control-allow-origin") == "https://astrocortex.example.org"
    from app.deps import reset_caches

    reset_caches()


def test_every_response_carries_a_request_id(client):
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
    assert len(client.get("/health").headers["X-Request-ID"]) == 12


def test_health_reports_degraded_when_a_dependency_fails(client, monkeypatch):
    class BrokenRepo:
        storage, persistent = "postgres", True

        def ping(self):
            return False

    monkeypatch.setattr("app.routers.meta.get_marks_repo", lambda: BrokenRepo())
    body = client.get("/health").json()
    assert body["status"] == "degraded" and body["checks"]["marks"] is False


def test_meta_declares_the_engines(client):
    """BR-CLS-01 and BR-MARK-02: the API says how its answers are produced and stored."""
    import json
    from pathlib import Path

    bundled = json.loads((Path(__file__).resolve().parents[1] / "models" / "metadata.json").read_text(encoding="utf-8"))
    body = client.get("/api/meta").json()
    assert body["classifier"] == {"method": "model", "version": bundled["model_version"], "calibrated": False}
    assert body["marks"] == {"storage": "memory", "persistent": False}


def test_unexpected_errors_return_500_with_request_id(client):
    """BR-ERR-01: no stack trace leaves the API; the request id does."""
    from app import deps

    def broken():
        raise RuntimeError("secret internals")

    client.app.dependency_overrides[deps.get_store] = broken
    r = client.get("/api/targets", headers={"X-Request-ID": "req42", "Origin": "http://localhost:5173"})
    client.app.dependency_overrides.clear()
    assert r.status_code == 500
    assert r.json() == {
        "error": {
            "code": "internal_error",
            "message": "Unexpected error. Report the request id.",
            "details": {"request_id": "req42"},
        }
    }
    assert "secret" not in r.text
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


# --- demo fields: sources, catalogs and agent tours (real ones are not produced yet) ---------


def test_sources_carry_review_status_and_summary(mock_client):
    """BR-CLS-05 through the API: summary matches the rows, needs_review comes first."""
    body = SourcesResponse.model_validate(mock_client.get("/api/sources", params={"field_id": "wise0855"}).json())
    assert body.method == "rule" and body.synthetic and not body.calibrated
    order = {"needs_review": 0, "classified": 1, "known": 2}
    statuses = [s.review_status.value for s in body.sources]
    assert statuses == sorted(statuses, key=order.get)
    assert body.summary.n_sources == len(body.sources)
    assert body.summary.needs_review == statuses.count("needs_review")
    assert body.sources[-1].source_id == "wise0855_s000" and body.sources[-1].review_status.value == "known"


def test_every_real_field_has_classified_sources_with_its_target(client):
    """BR-CLS-05/06: every published field answers, its target is a row, the summary matches the rows."""
    from app.domain.vocab import ReviewReason

    closed = {r.value for r in ReviewReason}
    for target in client.get("/api/targets").json():
        body = SourcesResponse.model_validate(
            client.get("/api/sources", params={"field_id": target["target_id"]}).json()
        )
        assert body.field_id == target["target_id"] and body.method == "model" and not body.synthetic
        assert body.catalogs_checked is True
        rows = body.sources
        assert body.summary.n_sources == len(rows)
        assert body.summary.needs_review == sum(r.review_status.value == "needs_review" for r in rows)
        targets = [r for r in rows if r.is_target]
        assert len(targets) == 1 and targets[0].catalog.status.value == "known_typed"
        epoch_ids = {e["epoch_id"] for e in client.get(target["static_manifest_url"]).json()["epochs"]}
        for r in rows:
            assert set(r.positions) == epoch_ids
            assert {x.value for x in r.review_reasons} <= closed


def test_wise0855_is_measured_as_a_red_moving_known_dwarf(client):
    """Measured on the real coadds: only seen in D5-D6, methane index >= 5, moves with the catalog motion."""
    rows = client.get("/api/sources", params={"field_id": "f_wise0855"}).json()["sources"]
    t = next(r for r in rows if r["is_target"])
    assert t["source_id"] == "wise0855_s00" and t["name"] == "WISE 0855-0714"
    assert (t["label"], t["review_status"], t["agreement"]) == ("cold_brown_dwarf", "known", "agrees")
    ev = t["evidence"]
    assert ev["detected_in"] == [5, 6] and ev["methane_index"] >= 5 and ev["in_gaia"] is False
    assert ev["in_catwise"] is True


def test_barnards_star_moves_north_about_1_6_px_in_a_year(client):
    rows = client.get("/api/sources", params={"field_id": "barnard"}).json()["sources"]
    t = next(r for r in rows if r["is_target"])
    assert t["label"] == "star" and t["review_status"] == "known"
    assert 1.4 < t["evidence"]["motion_px"] < 2.0
    p = t["positions"]
    assert p["e3"]["y"] < p["e1"]["y"] - 1.4  # row 0 is north: moving north lowers y


def test_catalog_layers_are_real_and_inside_the_cutout(client):
    body = CatalogsResponse.model_validate(client.get("/api/catalogs", params={"field_id": "barnard"}).json())
    assert body.field_id == "barnard" and not body.synthetic and body.gaia and body.wise
    centre = client.get("/api/field", params={"target_id": "barnard"}).json()["center"]
    for row in body.gaia:
        assert abs(row.dec - centre["dec"]) < 2.0 / 60


def test_catalogs(mock_client):
    body = CatalogsResponse.model_validate(mock_client.get("/api/catalogs", params={"field_id": "wise0855"}).json())
    assert body.gaia and body.wise


def test_marks_roundtrip(client):
    mark = {
        "field_id": "f_wise0855",
        "source_id": "wise0855_s000",
        "ra": 133.76,
        "dec": -7.24,
        "epoch_mjd": 61005.5,
        "user_label": "real",
    }
    created = client.post("/api/marks", json=mark)
    assert created.status_code == 201 and created.json()["mark_id"] == 1
    listed = client.get("/api/marks", params={"field_id": "wise0855"}).json()
    assert len(listed) == 1 and listed[0]["user_label"] == "real"
    assert listed[0]["field_id"] == "wise0855"  # BR-FIELD-06: stored under the canonical id
    assert client.post("/api/marks", json={**mark, "user_label": "maybe"}).status_code == 400
    unknown = client.post("/api/marks", json={**mark, "field_id": "nowhere"})
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "field_not_found"


def test_agent_builds_a_tour_from_the_real_field(client):
    """BR-AGENT-01/02: closed vocabulary, ids that exist, numbers from this API."""
    r = client.post("/api/agent", json={"message": "Guide me", "view_state": {"target_id": "f_wise0855"}})
    body = AgentResponse.model_validate(r.json())
    assert body.mode == "rule" and not body.recorded and len(body.steps) >= 4
    actions = [a for s in body.steps for a in s.actions]
    assert {"select_target", "play_flipbook", "blink", "show_detector_grid", "select_source"} <= {
        a.type for a in actions
    }
    assert actions[0].model_dump()["target_id"] == "wise0855"
    source_ids = {s["source_id"] for s in client.get("/api/sources", params={"field_id": "wise0855"}).json()["sources"]}
    epoch_ids = {"e1", "e2", "e3"}
    for a in actions:
        d = a.model_dump()
        if "source_id" in d:
            assert d["source_id"] in source_ids
        for key in ("epoch_id", "epoch_a", "epoch_b"):
            if key in d:
                assert d[key] in epoch_ids
    text = " ".join(s.say for s in body.steps)
    assert "D5, D6" in text and "discover" not in text.lower()
    assert "/api/sources?field_id=wise0855" in body.sources_used


def test_agent_explains_the_selected_source(client):
    rows = client.get("/api/sources", params={"field_id": "epsindib"}).json()["sources"]
    target = next(r for r in rows if r["is_target"])
    r = client.post(
        "/api/agent",
        json={
            "message": "Explain the selected source",
            "view_state": {"target_id": "epsindib", "selected_source_id": target["source_id"]},
        },
    )
    body = AgentResponse.model_validate(r.json())
    assert body.steps[0].actions[0].model_dump() == {"type": "select_source", "source_id": target["source_id"]}
    assert "Epsilon Indi B" in body.reply and "methane index" in body.reply


def test_agent_without_a_field_starts_with_a_test_target(client):
    body = client.post("/api/agent", json={"message": "hi"}).json()
    assert body["mode"] == "rule" and body["reply"].startswith("No field is open")


def test_agent_on_demo_fields(mock_client):
    r = mock_client.post("/api/agent", json={"message": "Guide me", "view_state": {"target_id": "wise0855"}})
    assert r.status_code == 200 and AgentResponse.model_validate(r.json()).steps


def test_agent_with_nothing_published_is_unavailable(tmp_path, monkeypatch):
    from tests.conftest import _make_client

    client = _make_client(monkeypatch, tmp_path)
    r = client.post("/api/agent", json={"message": "hi"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "agent_unavailable"


def test_static_tours_are_served_for_the_frontend_fallback(client):
    r = client.get("/static/agent/wise0855.json")
    assert r.status_code == 200 and AgentResponse.model_validate(r.json()).steps


def test_meta_lists_the_review_reason_texts(client):
    from app.domain.vocab import ReviewReason

    texts = client.get("/api/meta").json()["review_reasons"]
    assert set(texts) == {r.value for r in ReviewReason}


@pytest.mark.parametrize("field", ["barnard", "epsindib", "rdra", "rwaur", "wise0855"])
def test_spectrum_and_lightcurve_are_served_in_the_format_the_viewer_plots(client, field):
    manifest = client.get(f"/api/field?target_id={field}").json()
    spec = client.get(manifest["spectrum_url"])
    curve = client.get(manifest["lightcurve_url"])
    assert spec.status_code == curve.status_code == 200
    spec, curve = spec.json(), curve.json()
    assert spec["kind"] == "spectrum" and spec["flux_unit"] == "mJy"
    assert spec["n_points"] == len(spec["data"]) and spec["n_points"] + len(spec["excluded"]) == spec["n_exposures"]
    for row in spec["data"]:
        assert 0.7 < row["wavelength_um"] < 5.1 and row["flux_err"] > 0
        assert row["epoch_id"] in {e["epoch_id"] for e in manifest["epochs"]}
    assert curve["kind"] == "lightcurve" and curve["x"] == "mjd"
    for row in curve["data"]:
        assert row["flux"] > 0 and row["flux_err"] > 0 and row["mjd"] > 60000


def test_wise0855_spectrum_peaks_beyond_4_um_and_matches_its_known_brightness(client):
    """Y dwarf: almost nothing below 3.5 um, the flux comes out at 4-5 um (W2 about 0.5 mJy)."""
    rows = client.get("/static/fields/wise0855/spectrum.json").json()["data"]
    short = [r["flux"] for r in rows if r["wavelength_um"] < 3.5]
    long = [r["flux"] for r in rows if 4.4 <= r["wavelength_um"] < 5.0]
    assert abs(sorted(short)[len(short) // 2]) < 0.1
    assert 0.25 < sorted(long)[len(long) // 2] < 0.8
