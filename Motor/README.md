# AstroCortex classification engine (`Motor/`)

Trains, evaluates and publishes the classifier ("motor clasificatorio") that `/api/sources` uses to tell
**cold brown dwarfs (T/Y)** from everything else in a SPHEREx field. Everything needed to rebuild it from the data in
this folder is here: code, configuration, notebooks, tests, the promoted model and its reports. The backend serves the
copy in `Backend/models/` (`python main.py publicar`).

## Layout

| Path | Content | MLOps role |
|---|---|---|
| `motor/` | SPHEREx download (IRSA SIA + S3), forced photometry, SPHEREx features, preprocessing, RF / XGBoost / MLP comparison, ONNX export, report | source package |
| `TY_PIPELINE/` | catalog cross-match (CatWISE, AllWISE, 2MASS, unWISE, Gaia), spatial split, EDA, variable importance (unchanged from the original pipeline) | source package |
| `config/motor.json` | every parameter: SPHEREx selection, photometry, preprocessing rules, model grids, experiments (the values used for the current model) | params |
| `dvc.yaml`, `dvc.lock` | stages `ty → spherex (frozen) → entrenar → promover`, with the hashes of the current run | pipeline |
| `main.py` | CLI: `ty`, `descargar`, `entrenar`, `promover`, `publicar`, `predecir`, `verificar` | entry point |
| `notebooks/` | 01 data exploration · 02 preprocessing · 03 model comparison · 04 batch prediction (executed with the real results) | analysis |
| `artifacts/models/actual/` | promoted model: `model.onnx`, `metadata.json`, `verificacion.json`, `PARA_BACKEND.md` | model registry |
| `artifacts/models/<version>/` | every promoted version, kept side by side | model registry |
| `reports/` | `INFORME_MOTOR.md`, `metrics/comparacion_global.csv`, per-experiment metrics, confusion matrices, permutation importance and the run logs | metrics |
| `tests/` | rules, offline SPHEREx stages with synthetic MEF files, model contract, backend copy = promoted model | tests |
| `datos_entrada/`, `datos_extra_TY/` | labelled objects (11 850), catalog batches with SHA-256 receipts | data |
| `resultados_TY/run_004/` | TY run used by the current model (`run_003`: previous reference run) | data |
| `salidas/` | outputs of every motor stage of the current run (SPHEREx index, photometry, features, model table, experiments, export) | data |
| `scripts/`, `docs/vast_*` | how the training run was executed on a rented Vast machine | operations |

The fitted estimators of each experiment (`salidas/5_modelos/*/modelo_*.joblib|.pt`, ~80 MB) are not committed: they are
rebuilt by `python main.py entrenar`, and the served model is the ONNX file in `artifacts/models`. Everything else is in git,
so the notebooks run on a fresh clone. DVC outputs are `cache: false`, so no DVC remote is needed.

## Current model

`artifacts/models/actual` → **`motor-rf-E_servible_binario-spherex-2026-11-16T0256`**

- Random Forest, classes `star` (star, M or L) and `cold_brown_dwarf` (T or Y).
- Features (the ones the backend can compute for any source): `cw_W1_W2`, `cw_mu`, `Hrpm_W2` from CatWISE2020 and the
  SPHEREx detector colours `spx_c21`, `spx_c32`, `spx_c43`, `spx_c54`, `spx_c65`, `spx_c64`, `spx_ch4`.
  Formulas: `artifacts/models/actual/metadata.json` → `feature_definitions`.
- Spatial cross-validation (dev, 697 objects): balanced accuracy 0.946, cold-dwarf precision 0.935, recall 0.938.
- External test (151 objects in sky cells never seen in training): balanced accuracy 0.958, cold-dwarf precision 0.949,
  recall 0.949 (95 % CI of recall 0.88–1.00). ONNX vs original model: max difference 3.4e-7.

Read these numbers with three caveats:

1. The model was trained on the subset with SPHEREx photometry, where 42 % of objects are cold dwarfs. In a real
   field they are far rarer, so the precision on the sky will be lower than on this test.
2. `cw_W1_W2` carries most of the signal (macro-F1 drops 0.30 when it is shuffled; all SPHEREx colours together, 0.09).
3. With every feature missing, the fill values give `cold_brown_dwarf` (0.78). The backend does not use the model for
   a source without `cw_W1_W2` and with fewer than three SPHEREx colours: it answers `unknown` (`insufficient_data`).

## Experiments (reports/metrics/comparacion_global.csv)

| Experiment | Features | Classes | Rows | Chosen | CV macro-F1 | Test macro-F1 |
|---|---|---|---|---|---|---|
| A | catalog core (21) | star, M, L, T, Y | all 11 815 | XGBoost | 0.781 | 0.781 (Y recall 0.5) |
| B | catalog core (21) | binary | all | RF | 0.938 | 0.936 |
| C | catalog core (21) | 5 classes | SPHEREx subset | RF | 0.750 | 0.773 |
| D | catalog core + SPHEREx (28) | 5 classes | SPHEREx subset | RF | 0.756 | 0.833 (Y recall 0.6) |
| E | servable (10) | binary | SPHEREx subset | RF | 0.946 | 0.958 |

C and D use the same rows, so D − C is what SPHEREx adds: +0.006 macro-F1 in CV and +0.06 on the (small) test.

## Serving

The backend loads the model in-process (`Backend/app/services/classifier.py`, `OnnxPredictor`) from
`Backend/models/model.onnx` + `metadata.json`, the copy that `python main.py publicar` writes. It is the default
classifier: with `MODEL_PATH` unset or empty Render serves it, and `MODEL_PATH=rule` goes back to the rule-based v0.
A separate model API was not added: on the free Render plan it would be a second service that sleeps on its own, and
every classification would add a network hop; in-process, `/api/sources` for a 52-source field takes about 14 ms with
the model and 10 ms with the rule.

Per source, `Backend/app/services/features.py` computes the ten inputs with the formulas above: CatWISE colour,
motion and reduced proper motion from the field's `catalogs.json` row (by `catwise_id`), SPHEREx colours from the
row's coadd photometry with S/N ≥ 3. They are returned in each source's `evidence`. Rules around the model:
JPL match → `asteroid_comet`, extended → `galaxy`, no CatWISE colour and fewer than three SPHEREx colours →
`unknown` (`insufficient_data`), cold-dwarf answer without motion → `unknown` (`methane_without_motion`, BR-CLS-04).

Result on the five published fields: WISE 0855 and Epsilon Indi B → cold brown dwarf (the rule-based v0 called
Epsilon Indi B a star), Barnard's Star and RW Aurigae → star, R Draconis → insufficient data (saturated, no CatWISE
counterpart). In the fields, sources with red W1 − W2 and catalog motion ≥ 100 mas/yr come out as cold-dwarf
candidates in `needs_review` (three in RW Aurigae, one in Barnard); without motion they go to `unknown`.

`python main.py predecir` applies the same fill-and-threshold rule for batch use and for the notebooks.

## Running

```bash
pip install -r requirements.txt            # training (torch: see scripts/instalar.sh)
pip install -r requirements-ci.txt         # tests and model contract only
pytest -q
python main.py ty                          # TY 00-04
python main.py descargar                   # SPHEREx (needs IRSA and S3; ~40 min with the settings used)
python main.py entrenar                    # preprocessing, models, export, report
python main.py promover                    # copy the export to artifacts/ and reports/
python main.py publicar                    # copy artifacts/models/actual to Backend/models (what the API serves)
python main.py verificar                   # check the promoted model contract
python main.py predecir in.csv out.csv     # batch prediction with the promoted model
dvc repro                                  # same chain through DVC (spherex stage frozen)
```

The training run of this version used the reduced SPHEREx selection now in `config/motor.json` (star 200, M 100, L 200,
T 300, all 50 Y; DR1 only; 3 exposures per detector; class-weight power 0.25; 2 permutations). It took about 40 min of
downloads and 15 min of training on a 32-core Vast machine; the logs are in `reports/logs/`.

## Rules fixed before looking at the test

Spatial split (whole sky cells), duplicates removed by position and by identical feature vectors, missing values
imputed with the training median of each fold (the same values travel as `fill_values`), no missing-value indicators
(missing catalogs reveal how the sample was built), outliers reported but not removed, class weights
(N/(K·n_c))^p instead of resampling, model chosen by CV macro-F1, test evaluated once.
Details: `docs/vast_LEEME.md`, section 5.

## Pending

- SPHEREx colours: training measured them per exposure, the backend on per-epoch coadds. On the two targets measured
  both ways (Epsilon Indi B, WISE 0855) the methane colours agree (`spx_c54` −1.21 vs −1.20, `spx_ch4` 0.48 vs 0.48
  for Epsilon Indi B) but the short-wavelength ones do not (`spx_c21` −0.61 vs −2.79). The model leans on `cw_W1_W2`,
  so the effect is small, but the next training run should use the backend's photometry for `spx_*`.
- CatWISE artefact flags: training dropped W1/W2 when `cc_flags`/`ab_flags` were not `0`. `features.py` applies the
  same rule when `catalogs.json` carries the flags, but `scripts/fetch_catalogs.py` does not request them yet.
