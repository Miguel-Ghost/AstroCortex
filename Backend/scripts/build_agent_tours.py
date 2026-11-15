"""static/agent/<target_id>.json: the guide's tour of each published field, for the frontend fallback.

    python -m scripts.build_agent_tours

The frontend reads /static/agent/<target_id>.json from its own site when the API does not answer;
the backend serves the same files. They are written by the rule-based guide from the same data
the API answers with, so the fallback never says anything the API would not.
"""

from __future__ import annotations

import json
import sys

from app.config import get_settings
from app.schemas import AgentRequest, ViewState
from app.services.classifier import load_predictor
from app.services.guide import Guide
from app.services.static_store import StaticStore


def main() -> int:
    settings = get_settings()
    store = StaticStore(settings.fields_dir, settings.targets_file)
    guide = Guide(store, load_predictor(settings.model_path), settings)
    out = settings.static_dir / "agent"
    out.mkdir(parents=True, exist_ok=True)
    for ref in store.fields():
        name = ref.target_id or ref.folder
        response = guide.answer(AgentRequest(message="Guide me", view_state=ViewState(target_id=name)))
        doc = {**response.model_dump(), "recorded": True, "mode": "recorded"}
        (out / f"{name}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{name}: {len(doc['steps'])} steps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
