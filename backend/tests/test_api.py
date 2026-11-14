from __future__ import annotations

from app.schemas import AgentResponse, CatalogsResponse, FieldManifest, SourcesResponse


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["classifier_method"] == "rule"
    assert body["checks"] == {"classifier": True, "static_fields": True, "marks": True}


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


def test_every_response_carries_a_request_id(client):
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
    assert len(client.get("/health").headers["X-Request-ID"]) == 12


def test_targets_lists_the_five_test_targets(client):
    targets = {t["target_id"]: t for t in client.get("/api/targets").json()}
    assert set(targets) == {"barnard", "epsindib", "wise0855", "rwaur", "rdra"}
    assert targets["wise0855"]["static_manifest_url"] == "/static/fields/wise0855/manifest.json"
    assert targets["barnard"]["static_manifest_url"] is None  # not built in the test data


def test_field_by_target_id(client):
    r = client.get("/api/field", params={"target_id": "wise0855"})
    assert r.status_code == 200
    manifest = FieldManifest.model_validate(r.json())
    assert manifest.synthetic and len(manifest.epochs) == 3


def test_field_from_the_statement_coordinate_finds_wise0855(client):
    """BR-FIELD-05: the 2010 coordinate finds the target; the centre is the propagated position."""
    # the challenge gives the 2010 position; the object is ~2' away from it today
    r = client.get("/api/field", params={"ra": 133.79513, "dec": -7.24515})
    assert r.status_code == 200 and r.json()["target_id"] == "wise0855"
    center = r.json()["center"]
    assert abs(center["ra"] - 133.79513) * 3600 > 60  # more than 1' away from the 2010 coordinate


def test_field_errors_use_the_error_format(client):
    """BR-ERR-01."""
    far = client.get("/api/field", params={"ra": 10.0, "dec": 10.0})
    assert far.status_code == 404 and far.json()["error"]["code"] == "field_not_available"
    missing = client.get("/api/field")
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "missing_position"
    bad = client.get("/api/field", params={"ra": 999, "dec": 0})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_request"


def test_sources_carry_review_status_and_summary(client):
    """BR-CLS-05 through the API: summary matches the rows, needs_review comes first."""
    body = SourcesResponse.model_validate(client.get("/api/sources", params={"field_id": "wise0855"}).json())
    assert body.method == "rule" and body.synthetic and not body.calibrated
    order = {"needs_review": 0, "classified": 1, "known": 2}
    statuses = [s.review_status.value for s in body.sources]
    assert statuses == sorted(statuses, key=order.get)
    assert body.summary.n_sources == len(body.sources)
    assert body.summary.needs_review == statuses.count("needs_review")


def test_catalogs(client):
    body = CatalogsResponse.model_validate(client.get("/api/catalogs", params={"field_id": "wise0855"}).json())
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
    assert client.post("/api/marks", json={**mark, "user_label": "maybe"}).status_code == 422


def test_agent_returns_the_recorded_tour(client):
    """BR-AGENT-01: only actions from the closed vocabulary reach the viewer."""
    r = client.post("/api/agent", json={"message": "Guide me", "view_state": {"target_id": "wise0855"}})
    body = AgentResponse.model_validate(r.json())
    assert body.recorded and body.steps
    assert {a.type for s in body.steps for a in s.actions} >= {"select_target", "blink", "show_detector_grid"}


def test_agent_without_tour_is_unavailable(client):
    r = client.post("/api/agent", json={"message": "hi"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "agent_unavailable"


def test_static_frames_are_served(client):
    png = client.get("/static/fields/wise0855/e1_d6.png")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    data = client.get("/static/fields/wise0855/e1_d6.f32")
    assert data.status_code == 200 and len(data.content) == 31 * 31 * 4


def test_cors_allows_the_frontend_origin(client):
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_validation_errors_list_every_problem(client):
    """BR-ERR-01: every validation error is reported in details."""
    r = client.get("/api/field", params={"ra": 999, "dec": -100})
    body = r.json()["error"]
    assert r.status_code == 422 and body["code"] == "invalid_request"
    assert {tuple(e["loc"]) for e in body["details"]["errors"]} == {("query", "ra"), ("query", "dec")}


def test_unexpected_errors_return_500_with_request_id(client, monkeypatch):
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
