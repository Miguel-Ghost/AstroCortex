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
  services/         static store, classifier (rule + ONNX), marks (Postgres/memory), agent
pipeline/           image pipeline (query, read, grid, epochs, coadd, render, build_field, synthetic)
scripts/            make_mock_static.py: demo data built with the real pipeline on synthetic exposures
data/targets.json   the 5 test targets with astrometry (positions propagated by proper motion)
data/static/fields/ precomputed products per field (manifest.json, PNG, .f32, sources, catalogs, agent tour)
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

```bash
# demo data (synthetic images, real format; every file says "synthetic": true)
python -m scripts.make_mock_static

# real data for one target (needs internet access to IRSA and S3; run it offline, not on Render)
python -m pipeline.build_field --target wise0855
```

Each field folder contains `manifest.json` (contract 7.2), `e<epoch>_d<detector>.png`,
`*_flags.png`, `*.f32` (float32, row 0 = north, NaN = no data), `sources.json`,
`catalogs.json` and `agent_tour.json`. URLs in the manifest are relative to the API host.

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

- `RulePredictor` (default): methane index F(3.83–4.41 µm)/F(3.20–3.45 µm) + motion. Provisional thresholds.
- `OnnxPredictor`: loads `MODEL_PATH` (`model.onnx`) and `metadata.json` from the model repo.

Contract for each model version: input float32 `[1, n_features]`, last output = class probabilities
`[1, n_classes]`; `metadata.json` with `model_version`, `features`, `classes`, `calibrated`,
`thresholds`, `fill_values` and optional `scaler`. The preprocessing used in training must be
described there so serving repeats it exactly.

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
| Live fields for any coordinate | TODO (`/api/field` returns 404 outside the 5 targets) |
| Real sources/features per field | TODO (photometry + catalog cross-match) |
| ONNX model | interface ready; model expected Sunday |
| Live LLM agent | TODO; recorded tours work |
| Difference images | frontend can use the `.f32` data; server-side PNG diffs TODO |

## Data credits

SPHEREx data from the NASA/IPAC Infrared Science Archive (IRSA). Cite the SPHEREx data release DOI used.
