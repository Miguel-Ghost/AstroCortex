from __future__ import annotations

from app.schemas import AgentResponse, CatalogsResponse, SourcesResponse, Target

WISE = {"ra": 133.75945, "dec": -7.24286, "fov_arcmin": 3}

# --- real fields (what Render serves) --------------------------------------------------------


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["classifier_method"] == "rule"
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


def test_field_ignores_fov_and_uses_true_angular_separation(client):
    """BR-FIELD-05: within 1 arcmin of the published centre, measured on the sphere."""
    # R Draconis is at dec +66.75: 0.03 deg of RA there is only ~0.71 arcmin on the sky -> covered
    near = client.get("/api/field", params={"ra": 248.16723 + 0.03, "dec": 66.75502, "fov_arcmin": 99})
    assert near.status_code == 200 and near.json()["target_id"] == "rdra"
    # 0.03 deg of RA at WISE 0855 (dec -7.2) is ~1.79 arcmin -> not covered
    far = client.get("/api/field", params={"ra": 133.75945 + 0.03, "dec": -7.24286})
    assert far.status_code == 404
    # the challenge's 2010 coordinate of WISE 0855 is ~2 arcmin from the field centre
    assert client.get("/api/field", params={"ra": 133.79513, "dec": -7.24515}).status_code == 404


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
    body = client.get("/api/meta").json()
    assert body["classifier"] == {"method": "rule", "version": "rule-v0", "calibrated": False}
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


def test_real_fields_have_no_sources_yet(client):
    r = client.get("/api/sources", params={"field_id": "wise0855"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "sources_not_available"


def test_catalogs(mock_client):
    body = CatalogsResponse.model_validate(mock_client.get("/api/catalogs", params={"field_id": "wise0855"}).json())
    assert body.gaia and body.wise


def test_marks_roundtrip(client):
    mark = {
        "field_id": "wise0855",
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
    assert client.post("/api/marks", json={**mark, "user_label": "maybe"}).status_code == 400


def test_agent_returns_the_recorded_tour(mock_client):
    """BR-AGENT-01: only actions from the closed vocabulary reach the viewer."""
    r = mock_client.post("/api/agent", json={"message": "Guide me", "view_state": {"target_id": "wise0855"}})
    body = AgentResponse.model_validate(r.json())
    assert body.recorded and body.steps
    assert {a.type for s in body.steps for a in s.actions} >= {"select_target", "blink", "show_detector_grid"}


def test_agent_without_tour_is_unavailable(client):
    r = client.post("/api/agent", json={"message": "hi"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "agent_unavailable"
