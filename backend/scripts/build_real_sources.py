"""sources.json for every published field, measured on its coadds and cross-matched with catalogs.json.

    python -m scripts.fetch_catalogs        # once, where there is internet (or --from-file)
    python -m scripts.build_real_sources    # all fields; or name them: barnard wise0855

The PSF width per detector is fitted on bright isolated stars of all fields together. Without
catalogs.json a field still gets its rows (detections and the target), marked catalog not_checked.
"""

from __future__ import annotations

import json
import sys
from statistics import median

from app.config import get_settings
from app.services.static_store import StaticStore
from pipeline.sources import PSF_SIGMA_DEFAULT, FieldMeasurer, build_sources


def psf_sigmas(store: StaticStore, settings) -> dict[int, float]:
    widths: dict[int, list[float]] = {d: [] for d in range(1, 7)}
    for ref in store.fields():
        meas = FieldMeasurer(settings.fields_dir / ref.folder, store.manifest(ref.field_id))
        for d, values in meas.fit_psf_sigmas().items():
            widths[d] += values
    return {d: (median(v) if len(v) >= 3 else PSF_SIGMA_DEFAULT[d]) for d, v in widths.items()}


def main(argv: list[str]) -> int:
    settings = get_settings()
    store = StaticStore(settings.fields_dir, settings.targets_file)
    sig = psf_sigmas(store, settings)
    print("PSF sigma (px):", {d: round(s, 3) for d, s in sig.items()})
    refs = [store.resolve(a) for a in argv] if argv else store.fields()
    for ref in refs:
        if ref is None:
            print("unknown field", file=sys.stderr)
            return 2
        folder = settings.fields_dir / ref.folder
        catalogs = store.read_json(ref.field_id, "catalogs.json")
        doc = build_sources(folder, store.targets.get(ref.target_id), catalogs, sig)
        (folder / "sources.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        target = next((s for s in doc["sources"] if s["is_target"]), None)
        print(f"{ref.field_id}: {len(doc['sources'])} sources; target evidence: {target and target['evidence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
