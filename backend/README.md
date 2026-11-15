# AstroCortex backend: SPHEREx flipbook API

Backend of the NASA Space Apps 2026 project for the **"Planet X and SPHEREx"** challenge.
It turns SPHEREx exposures into a short, aligned animation (flipbook) of any small sky field,
classifies the sources in that field and serves everything to the web viewer.

- **API:** FastAPI, deployed on Render (free web service, region Virginia).
- **Image pipeline:** IRSA SIA (index) + AWS S3 (pixels) → common grid → epochs → coadds → PNG/float32 + manifest.
- **Classification engine:** one interface; rule-based v0 today (methane index + motion), ONNX model later.
- **Agent:** recorded tours today; live LLM agent planned.

## Layout

```
app/                FastAPI application
  main.py           app factory, CORS, /health, /static
  schemas.py        API contracts (mirror section 7 of the frontend guide)
  routers/          /api/targets, /api/field, /api/sources, /api/catalogs, /api/marks, /api/agent
  services/         static store (field index), classifier (rule + ONNX), engine, guide (rule agent),
                    live fields, marks (Postgres/memory)
pipeline/           image pipeline (query, read, grid, epochs, coadd, render, build_field, synthetic)
                    and sources.py (forced PSF photometry + catalog cross-match on the coadds)
scripts/            fetch_catalogs, build_real_sources, build_agent_tours, make_mock_static (demo data)
data/targets.json   the 5 test targets with astrometry (positions propagated by proper motion)
static/fields/      real SPHEREx fields of the 5 targets: manifest.json, PNG, flags PNG, float32 .bin,
                    catalogs.json (Gaia DR3 + CatWISE2020), sources.json (measured sources)
static/agent/       the guide's tour of each field (frontend fallback), served at /static/agent
tests/              pytest suite (API, classifier, pipeline on synthetic SPHEREx-like FITS)
```

## Run locally

All commands run from the `backend/` folder.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload          # http://localhost:8000/docs
pytest                                  # full test suite
```

## Data for the 5 test targets

Everything Render serves is committed: nothing is generated at runtime (its disk is rebuilt on deploy).

```bash
python -m scripts.fetch_catalogs        # Gaia DR3 + CatWISE2020 per field (needs internet; NOIRLab Data Lab)
python -m scripts.build_real_sources    # sources.json per field, measured on the coadds
python -m scripts.build_agent_tours     # static/agent/<target_id>.json
python -m scripts.make_mock_static      # demo fields for the tests (data/mock, never static/fields)
python -m pipeline.build_field --target wise0855   # rebuild a field from IRSA + S3 (offline)
```

Each real field folder contains `manifest.json`, `e<k>_d<n>.png`, `e<k>_d<n>_flags.png` and `e<k>_d<n>.bin`
(float32 little-endian, 31x31, row 0 = north, NaN = no data). URLs in the manifest start with
`/static/fields/<target_id>/` and are relative to the API host.

### Finding a field (`GET /api/field?ra=&dec=`)

The manifest is returned unchanged when (ra, dec) is within 1 arcmin of a field centre **or of the
target's proper-motion track between 1990 and 2030**, so a catalog coordinate of any epoch (the
challenge's 2010 coordinate of WISE 0855, J2000 tables) opens the field where the target is now.
How it matched travels in headers exposed by CORS: `X-Field-Match` (`center`, `track`, `target`,
`live`), `X-Field-Match-Epoch`, `X-Field-Offset-Arcmin`, `X-Target-Id`. Field names resolve from
the manifest `field_id`, the `target_id`, the folder or any alias (`f_wise0855`, `wise0855`,
`WISE 0855` are the same field) in every route.

### Live fields (`LIVE_FIELDS=true`)

Any other position gets a field built on request with the same pipeline: IRSA SIA (spherex_dr1,
spherex_qr3), at most 6 exposures per epoch and detector, partial reads from S3, coadd and manifest
with `field_id` `live_<ra>_<dec>` and `expected_position: null`, cached on disk per 0.01 deg cell and
served at `/static/live/`. A request waits at most `LIVE_TIMEOUT_S` (60 s, then 504
`live_field_timeout` while the build finishes in the background); IRSA down is 503
`upstream_unavailable`; no exposures is 404 `no_coverage`.

### Sources of a field (`pipeline/sources.py`)

Rows are Gaia DR3 / CatWISE2020 objects inside the cutout, placed at the date of each epoch with
their proper motion, plus SPHEREx detections without counterpart; only objects SPHEREx sees
(S/N >= 3 in some detector) are rows, and the target always is. Fluxes come from joint forced
photometry with a pixel-integrated Gaussian PSF per detector (width fitted on bright isolated stars),
so blends are separated; motion is a per-epoch position fit, reported above 3 sigma for sources not
dominated by a neighbour. `methane_index` = F(D5)/F(D4) (a lower limit when D4 is not detected).
Without catalogs a field still gets its rows, with `catalog.status = not_checked`.

## How the pipeline works

1. **query** – ask IRSA SIA which exposures cover the position (index only, cached, retries on 503/429).
2. **read** – read only a small window of IMAGE, VARIANCE, FLAGS and ZODI from S3 with fsspec block caching; subtract ZODI.
3. **grid** – resample every cutout onto one north-up, east-left grid with a **fixed centre** (target propagated to the median date). Without this, the blink shows jumps from each exposure's pointing and rotation instead of real motion.
4. **epochs** – group exposures into visits (gap > 10 days, max span 30 days).
5. **coadd** – inverse-variance mean per epoch and detector; SOURCE/OUTLIER flags are never excluded (moving objects carry them).
6. **render** – one fixed stretch per detector across all epochs (brightness changes stay real), PNG + float32.
7. **manifest** – per epoch: frames and the expected position of the target (the crosshair).

## Classification engine

`app/services/classifier.py` defines the interface used by `/api/sources`:

- `RulePredictor` (default): methane index (D5/D4 on the coadds) + motion. Provisional thresholds.
- `OnnxPredictor`: loads `MODEL_PATH` (`model.onnx`) and `metadata.json` from the model repo.

Contract for each model version: input float32 `[1, n_features]`, last output = class probabilities
`[1, n_classes]`; `metadata.json` with `model_version`, `features`, `classes`, `calibrated`,
`thresholds`, `fill_values` and optional `scaler`. The preprocessing used in training must be
described there so serving repeats it exactly.

## Guide agent (`POST /api/agent`)

- **Rule-based guide** (always available): tours, explanations and review queues built from the
  manifest and the classified sources.
- **Live agent** (when `LLM_API_KEY` and `LLM_MODEL` are set): the language model reads a context
  built from this API, picks the intent (tour, navigate, explain_source, review, answer) and writes
  the reply in the user's language; the steps still come from the rule-based guide. Unknown ids are
  dropped, and a reply with a number that is not in the data is replaced by the guide's text
  (`mode: "rule"`). Any failure falls back to the rule-based guide.
- **Provider** = configuration: any OpenAI-compatible `/chat/completions` endpoint
  (`LLM_BASE_URL`, default Gemini's), `LLM_MODEL`, optional `LLM_FALLBACK_MODELS`, `LLM_REASONING_EFFORT` (default `low`, dropped if a model rejects it), total budget
  `LLM_TIMEOUT_S` (6 s). The key lives only in Render.
- **Limits**: `AGENT_RPM_PER_IP` (20/min, then 429 `rate_limited`); model budget per client
  `LLM_RPM_PER_IP` (6/min), `LLM_RPD_PER_IP` (100/day) and global `LLM_DAILY_MAX` (1000/day),
  beyond which the rule-based guide answers. `GET /api/meta` reports `agent.mode`.

## Deploy on Render

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, pick the repo; it reads `render.yaml` at the repo root (`rootDir: backend`).
3. Set `CORS_ORIGINS` to the Vercel URL of the frontend.
4. Check `https://<service>.onrender.com/health`.

Free instances (512 MB RAM, 0.1 CPU) spin down after 15 minutes without traffic and take about a
minute to wake up. Use the Starter plan or an external ping during the demo.

## Status

| Part | State |
|---|---|
| API contracts, static fields, marks, CORS, error format | done, tested |
| Pipeline (grid, epochs, coadd, render, manifest) | done, tested on synthetic FITS |
| IRSA SIA query and S3 reads | written, **not yet tested against IRSA/S3** |
| Field lookup (centre or catalog track), field-id resolution | done, tested |
| Real sources per field (forced photometry + Gaia/CatWISE) | done for the 5 targets, tested |
| Live fields for any coordinate | written behind `LIVE_FIELDS`, tested with synthetic exposures; **IRSA/S3 path not yet run** |
| ONNX model | interface ready; model not trained yet (`method: "rule"` until then) |
| Guide agent | rule-based guide + live agent (model intent and reply, rule steps), tested with a fake model |
| Difference images | frontend uses the `.bin` data |

## Data credits

SPHEREx data from the NASA/IPAC Infrared Science Archive (IRSA). Cite the SPHEREx data release DOI used.
