"""Guide agent endpoint (section 9 of the frontend guide)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.deps import get_predictor, get_store
from app.errors import ApiError
from app.schemas import AgentRequest, AgentResponse
from app.services.agent import run_live_agent, sanitize
from app.services.classifier import Predictor
from app.services.guide import Guide
from app.services.static_store import StaticStore

router = APIRouter(prefix="/api", tags=["agent"])
log = logging.getLogger("api")


@router.post("/agent", response_model=AgentResponse)
def agent(
    request: AgentRequest,
    store: StaticStore = Depends(get_store),
    predictor: Predictor = Depends(get_predictor),
    settings: Settings = Depends(get_settings),
) -> AgentResponse:
    """Live LLM agent when configured; otherwise (or when it fails) the rule-based guide (BR-AGENT-03)."""
    if settings.llm_api_key:
        try:
            response = run_live_agent(request, settings.llm_api_key)
            response.mode = "live"
            return response
        except NotImplementedError:
            pass
        except Exception:  # noqa: BLE001 - a provider failure must not leave the user without a guide
            log.exception("live agent failed; answering with the rule-based guide")
    response = Guide(store, predictor, settings).answer(request)
    if response is not None:
        return response
    target_id = request.view_state.target_id
    tour = store.read_json(target_id, "agent_tour.json") if target_id else None
    if tour is not None:
        recorded = sanitize({**tour, "recorded": True})
        recorded.mode = "recorded"
        return recorded
    raise ApiError(503, "agent_unavailable", "No field is published, so the guide has nothing to show.")
