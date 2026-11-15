"""Rule-based guide: tours and explanations built from this API's own data, no language model needed.

Every number it says comes from the field manifest, the classified sources or the target catalog
(BR-AGENT-02), and every action it emits belongs to the closed vocabulary (BR-AGENT-01). The live
LLM agent, when configured, sits in front of it; this planner is what answers when there is no key
or the model fails, and what writes the static tours the frontend keeps as its own fallback.
"""

from __future__ import annotations

import re
from datetime import date

from app.config import Settings
from app.domain.vocab import REVIEW_REASON_TEXT
from app.schemas import AgentRequest, AgentResponse
from app.services.agent import sanitize
from app.services.classifier import Predictor
from app.services.engine import classify_field
from app.services.static_store import StaticStore

DEFAULT_TARGET = "wise0855"
CLASS_TEXT = {
    "star": "a star",
    "galaxy": "a galaxy",
    "asteroid_comet": "a candidate asteroid or comet",
    "cold_brown_dwarf": "a candidate cold brown dwarf",
    "unknown": "not classifiable with the current evidence",
}
KNOWN_TEXT = {
    "star": "star",
    "galaxy": "galaxy",
    "asteroid_comet": "asteroid or comet",
    "cold_brown_dwarf": "cold brown dwarf",
}
AGREEMENT_TEXT = {"agrees": "agrees with", "disagrees": "disagrees with"}
_EXPLAIN = re.compile(r"\b(explain|why|what is (this|it)|selected|explica|por ?qu[eé]|seleccionad)", re.I)
_REVIEW = re.compile(r"\b(review|revis|candidat|vote|vot)", re.I)


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _detectors(dets: list[int]) -> str:
    return ", ".join(f"D{d}" for d in dets) if dets else "none"


class Guide:
    def __init__(self, store: StaticStore, predictor: Predictor, settings: Settings):
        self.store, self.predictor, self.settings = store, predictor, settings

    # -- entry point ----------------------------------------------------------------------------
    def context(self, view_state) -> dict | None:
        """The field the request is about, with its manifest and classified sources (all from this API)."""
        ref = self.store.resolve(view_state.target_id) if view_state.target_id else None
        note = ""
        if ref is None and view_state.ra is not None and view_state.dec is not None:
            match = self.store.locate(view_state.ra, view_state.dec, self.settings.target_match_arcmin)
            ref = self.store.resolve(match.target_id) if match else None
        if ref is None:
            ref = self.store.resolve(DEFAULT_TARGET) or next(iter(self.store.fields()), None)
            if ref is None:
                return None
            note = "No field is open, so the tour starts with a test target. "
        manifest = self.store.manifest(ref.field_id)
        if manifest is None:
            return None
        sources = classify_field(ref.field_id, self.store, self.predictor, self.settings)
        used = ["/api/targets", f"/api/field?target_id={ref.target_id or ref.field_id}"]
        if sources:
            used.append(f"/api/sources?field_id={ref.field_id}")
        rows = (sources or {}).get("sources", [])
        selected = next((s for s in rows if s["source_id"] == view_state.selected_source_id), None)
        return {"ref": ref, "manifest": manifest, "sources": sources, "selected": selected, "note": note, "used": used}

    def build(self, ctx: dict, intent: str, source_id: str | None = None) -> dict:
        """Steps for an intent: tour, explain_source, review. Unknown ids fall back to the tour."""
        rows = (ctx["sources"] or {}).get("sources", [])
        if intent == "explain_source":
            row = next((s for s in rows if s["source_id"] == source_id), None) or ctx["selected"]
            if row is not None:
                return self.explain(ctx["manifest"], ctx["sources"], row)
        if intent == "review" and rows:
            return self.review(ctx["manifest"], ctx["sources"])
        return self.tour(ctx["ref"], ctx["manifest"], ctx["sources"])

    def respond(self, ctx: dict, raw: dict, mode: str = "rule") -> AgentResponse:
        raw = {**raw, "reply": ctx["note"] + raw["reply"], "sources_used": ctx["used"]}
        response = sanitize(raw)
        response.mode = mode
        return response

    def answer(self, request: AgentRequest) -> AgentResponse | None:
        ctx = self.context(request.view_state)
        if ctx is None:
            return None
        if ctx["selected"] and _EXPLAIN.search(request.message):
            intent = "explain_source"
        elif _REVIEW.search(request.message):
            intent = "review"
        else:
            intent = "tour"
        return self.respond(ctx, self.build(ctx, intent, request.view_state.selected_source_id))

    # -- pieces ---------------------------------------------------------------------------------
    def _epochs(self, manifest: dict, detector: int | None) -> list[dict]:
        eps = manifest.get("epochs", [])
        if detector is None:
            return [e for e in eps if e.get("frames")]
        return [e for e in eps if any(f["detector"] == detector for f in e.get("frames", []))]

    def _target_row(self, sources: dict | None) -> dict | None:
        return next((s for s in (sources or {}).get("sources", []) if s.get("is_target")), None)

    def _class_sentence(self, row: dict, sources: dict) -> str:
        method = "rule-based engine" if sources.get("method") == "rule" else f"model {sources.get('model_version')}"
        label = CLASS_TEXT.get(row["label"], row["label"])
        cat = row.get("catalog") or {}
        if cat.get("known_label"):
            verdict = AGREEMENT_TEXT.get(row["agreement"], "has no reference in")
            known = KNOWN_TEXT.get(cat["known_label"], cat["known_label"])
            source = cat.get("known_source")
            return f"The {method} labels it {label}; that {verdict} the catalog type ({known}, {source})."
        return f"The {method} labels it {label}; no catalog type exists for it."

    def _reasons(self, row: dict) -> str:
        texts = [REVIEW_REASON_TEXT.get(r, r.replace("_", " ")) for r in row.get("review_reasons", [])]
        return "; ".join(texts) if texts else "none"

    def tour(self, ref, manifest: dict, sources: dict | None) -> dict:
        target = self.store.targets.get(ref.target_id or "")
        dets = [d["detector"] for d in manifest.get("detectors", [])] or [1]
        det = target.default_detector if target and target.default_detector in dets else dets[0]
        eps = self._epochs(manifest, det) or self._epochs(manifest, None)
        first, last = eps[0], eps[-1]
        span = _days(first["date_iso"], last["date_iso"])
        name = target.name if target else manifest.get("field_id")
        lam = next((d for d in manifest.get("detectors", []) if d["detector"] == det), None)
        lam_txt = f" ({lam['lambda_min_um']}–{lam['lambda_max_um']} µm)" if lam else ""
        row = self._target_row(sources)
        ev = (row or {}).get("evidence") or {}
        steps = []

        intro = f"This is {name}."
        if target and target.short_description:
            intro = f"This is {name}: {target.short_description}"
        steps.append(
            {
                "say": f"{intro} SPHEREx imaged it on {len(eps)} dates in D{det}, from {first['date_iso']} to "
                f"{last['date_iso']} ({span} days). The view starts on D{det}{lam_txt}.",
                "actions": [
                    {"type": "select_target", "target_id": ref.target_id or ref.field_id},
                    {"type": "set_detector", "detector": det},
                    {"type": "set_epoch", "epoch_id": first["epoch_id"]},
                ],
            }
        )

        moving = bool(target and target.motion_arcsec_yr > 0.5)
        if moving and len(eps) >= 2:
            years = span / 365.25
            expected = target.motion_arcsec_yr * years / float(manifest.get("pixscale_arcsec", 6.2))
            measured, between = ev.get("motion_px"), ev.get("motion_epochs") or []
            dates = {e["epoch_id"]: e["date_iso"] for e in manifest.get("epochs", [])}
            if measured and len(between) == 2 and between[0] in dates and between[1] in dates:
                d_pair = _days(dates[between[0]], dates[between[1]]) / 365.25
                pred = target.motion_arcsec_yr * d_pair / float(manifest.get("pixscale_arcsec", 6.2))
                meas_txt = (
                    f" Measured between {dates[between[0]]} and {dates[between[1]]}, the dates where it is bright "
                    f"enough to fit: {measured} px, against {pred:.1f} px expected for that interval."
                )
            else:
                meas_txt = " It is too faint to fit its position on every date, so follow the crosshair."
            steps.append(
                {
                    "say": f"Play the dates in order. At {target.motion_arcsec_yr}″/yr it should move about "
                    f"{expected:.1f} px (pixels are 6.2″) between the first and last date; the crosshair marks "
                    f"where the catalog motion puts it on each date.{meas_txt}",
                    "actions": [{"type": "play_flipbook", "fps": 2}],
                }
            )
        elif len(eps) >= 2:
            steps.append(
                {
                    "say": "Play the dates in order. This object does not move at SPHEREx scale; look at its "
                    "brightness from one date to the next.",
                    "actions": [{"type": "play_flipbook", "fps": 2}],
                }
            )
        if len(eps) >= 2:
            steps.append(
                {
                    "say": f"Blink compares two dates directly: {first['date_iso']} against {last['date_iso']}. "
                    "A moving source jumps; a still one only changes brightness, if at all.",
                    "actions": [
                        {"type": "pause"},
                        {"type": "blink", "epoch_a": first["epoch_id"], "epoch_b": last["epoch_id"]},
                    ],
                }
            )

        detected = ev.get("detected_in") or []
        all_dets = [d["detector"] for d in manifest.get("detectors", [])]
        missing = [d for d in all_dets if d not in detected]
        grid_say = "The six detectors cover 0.75–5.0 µm, from left to right."
        if row:
            grid_say += f" In the measurements it is detected in {_detectors(detected)}"
            grid_say += f" and not in {_detectors(missing)}." if missing else "."
            mi = ev.get("methane_index")
            if mi is not None:
                limit = "at least " if ev.get("methane_index_lower_limit") else ""
                grid_say += (
                    f" Its D5/D4 flux ratio (methane index) is {limit}{mi:.1f}; ordinary stars sit near 0.5–1.5 "
                    "and methane-rich cold dwarfs far above."
                )
        steps.append({"say": grid_say, "actions": [{"type": "show_detector_grid"}]})

        if ev.get("variable") and len(eps) >= 2:
            steps.append(
                {
                    "say": f"Its flux changes between dates beyond the noise. The difference image "
                    f"{last['date_iso']} minus {first['date_iso']} shows it: white is brighter in the later date.",
                    "actions": [
                        {"type": "set_detector", "detector": det},
                        {"type": "show_difference", "epoch_a": first["epoch_id"], "epoch_b": last["epoch_id"]},
                    ],
                }
            )
        if ev.get("saturated") or (ev.get("flagged_frac") or 0) > 0.05:
            steps.append(
                {
                    "say": "Its core is saturated in some detectors: those pixels have no data and are shown in "
                    "purple. The flags layer marks the pixels the SPHEREx pipeline flagged.",
                    "actions": [{"type": "toggle_layer", "layer": "flags", "on": True}],
                }
            )

        if row and sources:
            steps.append(
                {
                    "say": self._class_sentence(row, sources),
                    "actions": [
                        {"type": "open_tab", "tab": "classification"},
                        {"type": "select_source", "source_id": row["source_id"]},
                    ],
                }
            )
            pending = [s for s in sources["sources"] if s["review_status"] == "needs_review" and not s.get("is_target")]
            summary = sources.get("summary", {})
            if pending:
                s = pending[0]
                steps.append(
                    {
                        "say": f"{summary.get('needs_review', len(pending))} of {summary.get('n_sources')} sources in "
                        f"this field need a human look. The first one, {s.get('name') or s['source_id']}, is flagged "
                        f"for: {self._reasons(s)}. Is it real or an artefact?",
                        "actions": [
                            {"type": "select_source", "source_id": s["source_id"]},
                            {"type": "ask_vote", "source_id": s["source_id"]},
                        ],
                    }
                )

        reply = f"Guided tour of {name}: {len(steps)} steps. Touch any control to take over."
        return {"reply": reply, "steps": steps}

    def explain(self, manifest: dict, sources: dict, row: dict) -> dict:
        ev = row.get("evidence") or {}
        eps = self._epochs(manifest, None)
        parts = [f"{row.get('name') or row['source_id']}."]
        parts.append(self._class_sentence(row, sources))
        facts = []
        if ev.get("detected_in"):
            facts.append(f"detected in {_detectors(ev['detected_in'])}")
        if ev.get("methane_index") is not None:
            limit = "at least " if ev.get("methane_index_lower_limit") else ""
            facts.append(f"methane index {limit}{ev['methane_index']:.2f}")
        if ev.get("motion_px"):
            facts.append(f"moves {ev['motion_px']} px in these images")
        elif ev.get("motion_px") == 0.0:
            facts.append("no motion measured")
        pm = ev.get("pm_mas_yr")
        if pm:
            facts.append(f"catalog proper motion ({pm['pmra']}, {pm['pmdec']}) mas/yr")
        if ev.get("in_gaia") is not None:
            facts.append("in Gaia" if ev["in_gaia"] else "not in Gaia")
        if ev.get("in_catwise") is not None:
            facts.append("in CatWISE" if ev["in_catwise"] else "not in CatWISE")
        if ev.get("variable"):
            facts.append("variable between dates")
        if facts:
            parts.append("Evidence: " + "; ".join(facts) + ".")
        if row["review_status"] == "needs_review":
            parts.append(f"It needs review because: {self._reasons(row)}.")
        actions = [{"type": "select_source", "source_id": row["source_id"]}]
        if len(eps) >= 2:
            actions.append({"type": "blink", "epoch_a": eps[0]["epoch_id"], "epoch_b": eps[-1]["epoch_id"]})
        steps = [{"say": " ".join(parts), "actions": actions}]
        if row["review_status"] != "known":
            steps.append(
                {
                    "say": "Your vote helps decide whether it is real.",
                    "actions": [{"type": "ask_vote", "source_id": row["source_id"]}],
                }
            )
        return {"reply": " ".join(parts), "steps": steps}

    def review(self, manifest: dict, sources: dict) -> dict:
        pending = [s for s in sources["sources"] if s["review_status"] == "needs_review"]
        eps = self._epochs(manifest, None)
        if not pending:
            return {
                "reply": "No source in this field needs review right now.",
                "steps": [
                    {"say": "Nothing to review here.", "actions": [{"type": "open_tab", "tab": "classification"}]}
                ],
            }
        steps = [
            {
                "say": f"{len(pending)} sources need review. Here are up to three.",
                "actions": [{"type": "open_tab", "tab": "classification"}],
            }
        ]
        for s in pending[:3]:
            actions = [{"type": "select_source", "source_id": s["source_id"]}]
            if len(eps) >= 2:
                actions.append({"type": "blink", "epoch_a": eps[0]["epoch_id"], "epoch_b": eps[-1]["epoch_id"]})
            actions.append({"type": "ask_vote", "source_id": s["source_id"]})
            steps.append({"say": f"{s.get('name') or s['source_id']}: {self._reasons(s)}.", "actions": actions})
        return {"reply": f"Review queue: {len(pending)} sources.", "steps": steps}
