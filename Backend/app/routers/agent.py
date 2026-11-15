"""Guide agent endpoint (section 9 of the frontend guide)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.config import Settings, get_settings
from app.deps import get_agent_limits, get_llm, get_predictor, get_store
from app.errors import ApiError
from app.schemas import AgentRequest, AgentResponse
from app.services.agent import sanitize
from app.services.classifier import Predictor
from app.services.guide import Guide
from app.services.live_agent import LiveAgent
from app.services.ratelimit import client_ip
from app.services.static_store import StaticStore

router = APIRouter(prefix="/api", tags=["agent"])
log = logging.getLogger("api")


@router.post("/agent", response_model=AgentResponse)
def agent(
    payload: AgentRequest,
    request: Request,
    store: StaticStore = Depends(get_store),
    predictor: Predictor = Depends(get_predictor),
    settings: Settings = Depends(get_settings),
) -> AgentResponse:
    """Live agent (language model + rule-based steps) when configured and within budget; otherwise,
    or when the model fails, the rule-based guide (BR-AGENT-03, BR-AGENT-04)."""
    ip = client_ip(request)
    limits = get_agent_limits()
    if not limits.allow_request(ip):
        raise ApiError(
            429,
            "rate_limited",
            "Too many questions in a short time. Wait a minute and try again.",
            {"retry_after_s": limits.requests.retry_after(ip)},
        )
    guide = Guide(store, predictor, settings)
    llm = get_llm()
    if llm is not None and limits.allow_llm(ip):
        try:
            response = LiveAgent(guide, llm).answer(payload)
            if response is not None:
                return response
        except Exception as exc:  # noqa: BLE001 - provider down, quota, timeout, bad JSON: the guide answers
            log.warning("live agent failed; rule-based guide answers", extra={"error": str(exc)[:300]})
    response = guide.answer(payload)
    if response is not None:
        return response
    target_id = payload.view_state.target_id
    tour = store.read_json(target_id, "agent_tour.json") if target_id else None
    if tour is not None:
        recorded = sanitize({**tour, "recorded": True})
        recorded.mode = "recorded"
        return recorded
    raise ApiError(503, "agent_unavailable", "No field is published, so the guide has nothing to show.")
