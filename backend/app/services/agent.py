"""Guide agent. Recorded tours work today; the live LLM agent is a TODO.

Design for the live version (keep it this narrow):
- tools the LLM may call = this API's own read endpoints (field, sources, catalogs, targets);
- the LLM answers ONLY with what those calls returned;
- output is parsed into AgentResponse; any action outside the closed vocabulary is dropped;
- the provider key lives only in the backend (LLM_API_KEY).
"""
from __future__ import annotations

from pydantic import ValidationError

from app.schemas import AgentAction, AgentRequest, AgentResponse, AgentStep


def sanitize(raw: dict) -> AgentResponse:
    """Keep only valid steps/actions from a tour or an LLM output."""
    steps = []
    for step in raw.get("steps", []):
        actions = []
        for action in step.get("actions", []):
            try:
                actions.append(AgentAction.model_validate(action))
            except ValidationError:
                continue  # unknown action type or bad parameters: ignore it
        steps.append(AgentStep(say=str(step.get("say", "")), actions=actions))
    return AgentResponse(reply=str(raw.get("reply", "")), steps=steps,
                         sources_used=list(raw.get("sources_used", [])), recorded=bool(raw.get("recorded", False)))


def run_live_agent(request: AgentRequest, api_key: str) -> AgentResponse:
    raise NotImplementedError("Live agent not implemented yet (planned for Sunday)")
