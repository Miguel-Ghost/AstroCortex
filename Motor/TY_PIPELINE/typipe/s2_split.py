"""Etapa 2: partición espacial fija ANTES de mirar relaciones con la etiqueta.

Celdas de área igual (bandas en sin(dec) × bins en RA). Un 20 % de las celdas
(estratificado por clase) queda como test externo, que solo se usa una vez al final.
El resto (desarrollo) se divide en pliegues de validación cruzada por celdas.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from .common import write_json
from .s1_features import load_saved, save_table


def sky_cells(ra, dec, n_dec: int, n_ra: int) -> np.ndarray:
    u = (np.sin(np.deg2rad(np.asarray(dec, float))) + 1) / 2
    band = np.clip((u * n_dec).astype(int), 0, n_dec - 1)
    rbin = np.clip((np.asarray(ra, float) % 360 / 360 * n_ra).astype(int), 0, n_ra - 1)
    return band * n_ra + rbin


def run(cfg: dict, out: Path, feat_dir: Path, log) -> dict:
    t = load_saved(feat_dir / "features")
    sc = cfg["split"]
    seed = int(cfg["seed"])
    groups = sky_cells(t["ra"], t["dec"], sc["sky_dec_bands"], sc["sky_ra_bins"])
    y = t["label"].to_numpy()
    chosen = None
    for attempt in range(25):
        sgkf = StratifiedGroupKFold(n_splits=sc["test_fraction_folds"], shuffle=True,
                                    random_state=seed + attempt)
        for dev_idx, test_idx in sgkf.split(t, y, groups):
            counts = pd.Series(y[test_idx]).value_counts()
            if counts.get("Y", 0) >= sc["min_y_in_test"] and counts.get("T", 0) >= 50:
                chosen = (dev_idx, test_idx, seed + attempt)
                break
        if chosen:
            break
    if chosen is None:
        raise RuntimeError("No se encontró partición espacial con suficientes Y en test")
    dev_idx, test_idx, used_seed = chosen
    role = np.full(len(t), "dev", dtype=object)
    role[test_idx] = "test"
    split = pd.DataFrame({"oid": t["oid"], "label": t["label"], "sky_cell": groups,
                          "role": role, "cv_fold": -1})
    dev = split.index[split["role"] == "dev"]
    cv = StratifiedGroupKFold(n_splits=sc["cv_folds"], shuffle=True, random_state=used_seed)
    for k, (_, va) in enumerate(cv.split(dev, y[dev], groups[dev])):
        split.loc[dev[va], "cv_fold"] = k
    save_table(split, out / "particion")
    test_cells = set(groups[test_idx])
    dev_cells = set(groups[dev_idx])
    summary = {
        "seed_used": used_seed,
        "cells_total": int(len(set(groups))), "cells_test": len(test_cells),
        "overlap_cells": len(test_cells & dev_cells),
        "dev_counts": split.loc[split.role == "dev", "label"].value_counts().to_dict(),
        "test_counts": split.loc[split.role == "test", "label"].value_counts().to_dict(),
        "cv_fold_counts": {int(k): v["label"].value_counts().to_dict()
                           for k, v in split[split.cv_fold >= 0].groupby("cv_fold")},
    }
    if summary["overlap_cells"]:
        raise RuntimeError("Celdas compartidas entre dev y test")
    write_json(out / "particion_resumen.json", summary)
    log.info("partición: test %s", summary["test_counts"])
    return {"summary": {k: summary[k] for k in ("cells_total", "cells_test", "test_counts")}}
