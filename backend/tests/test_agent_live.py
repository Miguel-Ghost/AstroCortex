"""Live agent: the model picks the intent and writes the reply; steps and numbers come from the data."""

from __future__ import annotations

import httpx
import pytest

from app.services.live_agent import grounded
from app.services.llm import LLMClient, LLMError, parse_json_object

GUIDE_ME = {"message": "Guide me", "view_state": {"target_id": "wise0855"}}


@pytest.fixture()
def live(monkeypatch):
    """API client with a configured model whose answers the test decides."""
    from tests.conftest import _make_client

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "fast-model")
    answers: list = []
    calls: list = []

    def fake_json(self, system, user, **kw):
        calls.append(user)
        out = answers.pop(0) if answers else {"intent": "tour", "reply": "Here is the tour."}
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(LLMClient, "json", fake_json)
    client = _make_client(monkeypatch, keep_llm=True)
    client.answers, client.calls = answers, calls
    yield client
    from app.deps import reset_caches

    reset_caches()


def test_model_reply_with_rule_steps(live):
    live.answers.append({"intent": "tour", "reply": "WISE 0855 moved 0.67 px between the first two dates."})
    body = live.post("/api/agent", json=GUIDE_ME).json()
    assert body["mode"] == "live" and body["reply"].startswith("WISE 0855 moved 0.67 px")
    actions = [a["type"] for s in body["steps"] for a in s["actions"]]
    assert actions[0] == "select_target" and "blink" in actions  # steps from the rule-based guide


def test_a_number_not_in_the_data_is_never_shown(live):
    """BR-AGENT-05."""
    live.answers.append({"intent": "tour", "reply": "It moved 42 px and is 7 billion years old."})
    body = live.post("/api/agent", json=GUIDE_ME).json()
    assert body["mode"] == "rule" and "42" not in body["reply"] and body["steps"]


def test_navigate_opens_another_target(live):
    live.answers.append({"intent": "navigate", "target_id": "barnard", "reply": "Opening Barnard's Star."})
    body = live.post("/api/agent", json={"message": "show me Barnard", "view_state": {"target_id": "wise0855"}}).json()
    first = body["steps"][0]["actions"][0]
    assert body["mode"] == "live" and first == {"type": "select_target", "target_id": "barnard"}


def test_unknown_ids_from_the_model_are_dropped(live):
    """BR-AGENT-02: a made-up source id never reaches the viewer."""
    live.answers.append({"intent": "explain_source", "source_id": "made_up", "reply": "No such source here."})
    body = live.post("/api/agent", json=GUIDE_ME).json()
    ids = [a.get("source_id") for s in body["steps"] for a in s["actions"]]
    assert "made_up" not in ids


def test_explains_the_selected_source_with_the_model_text(live):
    rows = live.get("/api/sources", params={"field_id": "epsindib"}).json()["sources"]
    t = next(r for r in rows if r["is_target"])
    live.answers.append({"intent": "explain_source", "source_id": t["source_id"], "reply": "Esta es Epsilon Indi B."})
    body = live.post(
        "/api/agent",
        json={
            "message": "explícame esta",
            "view_state": {"target_id": "epsindib", "selected_source_id": t["source_id"]},
        },
    ).json()
    assert body["reply"] == "Esta es Epsilon Indi B."
    assert body["steps"][0]["actions"][0] == {"type": "select_source", "source_id": t["source_id"]}


def test_model_failure_falls_back_to_the_rule_guide(live):
    """BR-AGENT-03."""
    live.answers.append(LLMError("HTTP 503"))
    r = live.post("/api/agent", json=GUIDE_ME)
    assert r.status_code == 200 and r.json()["mode"] == "rule" and r.json()["steps"]


def test_context_sent_to_the_model_holds_the_measured_facts(live):
    live.post("/api/agent", json=GUIDE_ME)
    sent = live.calls[-1]
    assert "wise0855_s00" in sent and "methane_index" in sent and "test-key" not in sent


def test_per_client_and_model_budgets(monkeypatch):
    """BR-AGENT-04: hard limit per client (429) and a model budget beyond which the rule guide answers."""
    from tests.conftest import _make_client

    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("AGENT_RPM_PER_IP", "3")
    monkeypatch.setenv("LLM_RPM_PER_IP", "1")
    calls = []
    monkeypatch.setattr(
        LLMClient, "json", lambda self, s, u, **kw: calls.append(1) or {"intent": "tour", "reply": "Hi."}
    )
    client = _make_client(monkeypatch, keep_llm=True)
    modes = [client.post("/api/agent", json=GUIDE_ME).json()["mode"] for _ in range(3)]
    assert modes == ["live", "rule", "rule"] and len(calls) == 1
    r = client.post("/api/agent", json=GUIDE_ME)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert r.json()["error"]["details"]["retry_after_s"] >= 1
    other = client.post("/api/agent", json=GUIDE_ME, headers={"X-Forwarded-For": "203.0.113.9"})
    assert other.status_code == 200  # another client has its own budget
    from app.deps import reset_caches

    reset_caches()


def test_meta_says_how_the_agent_answers_without_the_key(live):
    agent = live.get("/api/meta").json()["agent"]
    assert agent == {"mode": "live", "provider": "generativelanguage.googleapis.com", "model": "fast-model"}


def test_grounding_check():
    ctx = '{"motion_px":0.67,"dates":["2025-05-06","2026-05-01"],"needs_review":7,"D5":"3.82-4.41 um"}'
    assert grounded("Moved 0.67 px; 7 sources need review; D5 covers 3.82-4.41 um.", ctx)
    assert grounded("Imaged on 2025-05-06.", ctx)
    assert not grounded("Moved 0.9 px.", ctx)
    assert grounded("It is a cold brown dwarf.", ctx)


# --- the HTTP client ------------------------------------------------------------------------------


def _client(handler, **kw):
    return LLMClient("k", "https://llm.test/v1", "main", ["backup"], transport=httpx.MockTransport(handler), **kw)


def _ok(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_client_falls_back_to_the_next_model_on_429():
    seen = []

    def handler(request):
        model = __import__("json").loads(request.content)["model"]
        seen.append(model)
        return httpx.Response(429) if model == "main" else _ok('{"intent": "tour", "reply": "ok"}')

    llm = _client(handler)
    assert llm.json("s", "u") == {"intent": "tour", "reply": "ok"} and seen == ["main", "backup"]
    assert llm.last_model == "backup"


def test_client_retries_without_json_mode_and_parses_fenced_json():
    bodies = []

    def handler(request):
        body = __import__("json").loads(request.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, text="response_format is not supported")
        return _ok('```json\n{"intent": "answer", "reply": "x"}\n```')

    assert _client(handler).json("s", "u")["intent"] == "answer" and len(bodies) == 2


def test_client_asks_for_low_reasoning_and_drops_it_when_unsupported():
    bodies = []

    def handler(request):
        body = __import__("json").loads(request.content)
        bodies.append(body)
        if "reasoning_effort" in body:
            return httpx.Response(400, text="Unknown name reasoning_effort")
        return _ok('{"intent": "tour", "reply": "ok"}')

    assert _client(handler, reasoning_effort="low").json("s", "u")["reply"] == "ok"
    assert bodies[0]["reasoning_effort"] == "low" and "reasoning_effort" not in bodies[1]


def test_client_bad_key_does_not_try_other_models():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, text="bad key")

    with pytest.raises(LLMError):
        _client(handler).json("s", "u")
    assert len(calls) == 1


def test_parse_json_object_finds_the_object_inside_text():
    assert parse_json_object('Sure! {"a": 1} hope it helps') == {"a": 1}
    with pytest.raises(LLMError):
        parse_json_object("no json here")
