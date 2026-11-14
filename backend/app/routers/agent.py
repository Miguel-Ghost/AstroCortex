"""Guide agent endpoint (section 9 of the frontend guide)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.deps import get_store
from app.errors import ApiError
from app.schemas import AgentRequest, AgentResponse
from app.services.agent import run_live_agent, sanitize
from app.services.static_store import StaticStore

router = APIRouter(prefix="/api", tags=["agent"])


@router.post("/agent", response_model=AgentResponse)
def agent(
    request: AgentRequest, store: StaticStore = Depends(get_store), settings: Settings = Depends(get_settings)
) -> AgentResponse:
    if settings.llm_api_key:
        try:
            return run_live_agent(request, settings.llm_api_key)
        except NotImplementedError:
            pass  # fall back to the recorded tour
    target_id = request.view_state.target_id
    tour = store.read_json(target_id, "agent_tour.json") if target_id else None
    if tour is not None:
        return sanitize({**tour, "recorded": True})
    raise ApiError(
        503, "agent_unavailable", "The live agent is not configured; recorded tours exist only for the 5 test targets"
    )
