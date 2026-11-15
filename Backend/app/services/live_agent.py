"""Live guide: the language model understands the question and writes the reply; the rule-based
guide builds the steps. The model never produces a number or an action on its own.

1. The context is built from this API only (field, target evidence, classified sources).
2. The model returns JSON: intent, optional target_id / source_id, and a short reply.
3. Ids are checked against the context; an unknown id is dropped (BR-AGENT-02).
4. Steps come from the rule-based guide for that intent, so every action is in the closed
   vocabulary and every number in a step comes from the data (BR-AGENT-01).
5. Every number in the reply must appear in the context; otherwise the reply is replaced by the
   guide's own text and the response says mode "rule" (BR-AGENT-05).
Any failure (timeout, quota, bad JSON) falls back to the rule-based guide (BR-AGENT-03).
"""

from __future__ import annotations

import json
import logging
import re

from app.schemas import AgentRequest, AgentResponse
from app.services.guide import Guide
from app.services.llm import LLMClient

log = logging.getLogger("api")
INTENTS = ("tour", "explain_source", "review", "navigate", "answer")
_NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:[.,]\d+)?")

SYSTEM = """You are Cortex, the guide of AstroCortex, a viewer of NASA SPHEREx infrared images.
You answer ONLY with facts present in CONTEXT (JSON). Never invent numbers, names, dates or sources.
If CONTEXT does not contain the answer, say so briefly and offer a guided tour.
Write the reply in the same language as the user's message, at most 70 words, plain text.
Never call a source a discovery: say "candidate" or "needs review".

Return ONLY a JSON object:
{"intent": "tour" | "explain_source" | "review" | "navigate" | "answer",
 "target_id": one of CONTEXT.targets[].target_id or null,
 "source_id": one of the source ids in CONTEXT or null,
 "reply": "..."}

Intents:
- tour: the user wants to be shown the open field ("guide me", "what am I looking at").
- navigate: the user asks to open another test target (set target_id).
- explain_source: the user asks about one source (set source_id; the selected one if unspecified).
- review: the user asks what needs review, candidates, or what to vote on.
- answer: a question answered by text alone, no movement in the viewer."""


def _numbers(text: str) -> set[str]:
    out = set()
    for raw in _NUMBER.findall(text):
        value = raw.replace(",", ".").lstrip("+")
        try:
            f = float(value)
        except ValueError:
            continue
        out.add(f"{f:g}")
        out.add(f"{round(f, 1):g}")
        out.add(f"{round(f, 2):g}")
        out.add(f"{round(f):g}")
    return out


def grounded(reply: str, context_text: str) -> bool:
    """True when every number written in the reply also appears in the context (any rounding)."""
    allowed = _numbers(context_text)
    for raw in _NUMBER.findall(reply):
        try:
            f = float(raw.replace(",", ".").lstrip("+"))
        except ValueError:
            continue
        if not ({f"{f:g}", f"{round(f, 1):g}", f"{round(f, 2):g}"} & allowed):
            return False
    return True


class LiveAgent:
    def __init__(self, guide: Guide, llm: LLMClient):
        self.guide, self.llm = guide, llm

    def facts(self, ctx: dict) -> dict:
        manifest, sources, ref = ctx["manifest"], ctx["sources"] or {}, ctx["ref"]
        rows = sources.get("sources", [])
        target = self.guide.store.targets.get(ref.target_id or "")
        trow = next((s for s in rows if s.get("is_target")), None)

        def brief(s: dict) -> dict:
            return {
                "source_id": s["source_id"],
                "name": s.get("name"),
                "label": s["label"],
                "review_status": s["review_status"],
                "review_reasons": s["review_reasons"],
                "catalog": {k: v for k, v in (s.get("catalog") or {}).items() if v is not None},
                "evidence": {k: v for k, v in (s.get("evidence") or {}).items() if v is not None},
            }

        return {
            "targets": [
                {"target_id": t.target_id, "name": t.name, "motion_arcsec_yr": t.motion_arcsec_yr}
                for t in self.guide.store.targets.values()
            ],
            "open_field": {
                "field_id": ref.field_id,
                "target": target.name if target else None,
                "description": target.short_description if target else None,
                "dates": [e["date_iso"] for e in manifest.get("epochs", [])],
                "detectors": {
                    f"D{d['detector']}": f"{d['lambda_min_um']}-{d['lambda_max_um']} um"
                    for d in manifest.get("detectors", [])
                },
                "pixel_arcsec": manifest.get("pixscale_arcsec"),
                "expected_shift_px_first_to_last_date": self._expected_shift(target, manifest),
            },
            "classifier": {
                "method": sources.get("method"),
                "calibrated": sources.get("calibrated"),
                "summary": sources.get("summary"),
            },
            "target_source": brief(trow) if trow else None,
            "needs_review": [brief(s) for s in rows if s["review_status"] == "needs_review"][:6],
            "selected_source": brief(ctx["selected"]) if ctx["selected"] else None,
        }

    @staticmethod
    def _expected_shift(target, manifest: dict) -> float | None:
        epochs = manifest.get("epochs", [])
        if not target or len(epochs) < 2 or not target.motion_arcsec_yr:
            return None
        years = (epochs[-1]["mjd_avg"] - epochs[0]["mjd_avg"]) / 365.25
        return round(target.motion_arcsec_yr * years / float(manifest.get("pixscale_arcsec", 6.2)), 1)

    def answer(self, request: AgentRequest) -> AgentResponse | None:
        ctx = self.guide.context(request.view_state)
        if ctx is None:
            return None
        facts = self.facts(ctx)
        context_text = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
        history = [
            {"role": h.get("role"), "content": str(h.get("content", ""))[:400]}
            for h in request.history[-6:]
            if h.get("role") in ("user", "assistant")
        ]
        user = json.dumps(
            {"CONTEXT": facts, "HISTORY": history, "MESSAGE": request.message[:1000]},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        out = self.llm.json(SYSTEM, user)

        intent = out.get("intent") if out.get("intent") in INTENTS else "tour"
        source_ids = {s["source_id"] for s in (ctx["sources"] or {}).get("sources", [])}
        source_id = out.get("source_id") if out.get("source_id") in source_ids else None
        target_id = out.get("target_id") if out.get("target_id") in self.guide.store.targets else None

        if intent == "navigate" and target_id and target_id != ctx["ref"].target_id:
            ctx = self.guide.context(request.view_state.model_copy(update={"target_id": target_id}))
            context_text += json.dumps(self.facts(ctx), ensure_ascii=False, separators=(",", ":"))
            intent = "tour"
        if intent == "navigate":
            intent = "tour"
        if intent == "explain_source" and not (source_id or ctx["selected"]):
            intent = "answer"

        raw = (
            {"reply": "", "steps": []}
            if intent == "answer"
            else self.guide.build(ctx, intent, source_id or request.view_state.selected_source_id)
        )
        reply = str(out.get("reply") or "").strip()
        if reply and grounded(reply, context_text):
            raw["reply"] = reply
            mode = "live"
        else:
            log.warning("live agent reply rejected (empty or ungrounded number); using the rule text")
            if not raw.get("steps"):
                raw = self.guide.build(ctx, "tour")
            mode = "rule"
        return self.guide.respond({**ctx, "note": ""}, raw, mode=mode)
