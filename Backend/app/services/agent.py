"""Agent output sanitizer shared by the rule-based guide, the live agent and recorded tours.

The live agent is in live_agent.py, the rule-based guide in guide.py.
"""

from __future__ import annotations

from pydantic import ValidationError

from app.schemas import AgentAction, AgentResponse, AgentStep


def sanitize(raw: dict) -> AgentResponse:
    """Keep only valid steps/actions from a tour or an LLM output (BR-AGENT-01)."""
    steps = []
    for step in raw.get("steps", []):
        actions = []
        for action in step.get("actions", []):
            try:
                actions.append(AgentAction.model_validate(action))
            except ValidationError:
                continue  # unknown action type or bad parameters: ignore it
        steps.append(AgentStep(say=str(step.get("say", "")), actions=actions))
    return AgentResponse(
        reply=str(raw.get("reply", "")),
        steps=steps,
        sources_used=list(raw.get("sources_used", [])),
        recorded=bool(raw.get("recorded", False)),
    )
