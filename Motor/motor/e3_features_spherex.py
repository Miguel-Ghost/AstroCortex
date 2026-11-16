"""Etapa 3 · Variables SPHEREx por objeto (feature engineering), a partir de la fotometría.

Por objeto y detector: flujo medio ponderado por inverso de la varianza (solo mediciones OK), su error,
S/N y λ mediana. Con eso, por objeto:
- colores AB entre detectores vecinos: spx_c21 = −2.5·log10(F_D2/F_D1), spx_c32, spx_c43, spx_c54, spx_c65,
  y spx_c64; solo si ambos detectores tienen S/N ≥ snr_color_min (si no, faltante);
- spx_ch4 = log10(F_D5/F_D4): el índice de metano del backend (F_D5/F_D4) en escala logarítmica.
  Mismo criterio que el backend: con D5 detectado y D4 no, el valor es un límite inferior (spx_ch4_limite = 1);
- AUDITORÍA (no son predictores: dependen del brillo y de la cobertura, como en TY_PIPELINE):
  spx_snr_max, spx_n_det (detectores con S/N ≥ snr_deteccion), spx_n_ok (mediciones OK).

Salidas (salidas/3_features_spherex/): features_spherex.parquet, controles_pilotos.csv, grupos_spherex.json,
resumen.json
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .comun import out_dir, save_parquet, write_json

PARES = [("c21", 2, 1), ("c32", 3, 2), ("c43", 4, 3), ("c54", 5, 4), ("c65", 6, 5), ("c64", 6, 4)]
GRUPOS = {
    "spherex_color": [f"spx_{n}" for n, _, _ in PARES] + ["spx_ch4"],
    "AUDIT_spherex": ["spx_snr_max", "spx_n_det", "spx_n_ok", "spx_ch4_limite"],
}


def agregar(ph: pd.DataFrame, snr_color: float, snr_det: float) -> pd.DataFrame:
    ok = ph[(ph["estado"] == "OK") & np.isfinite(ph["flux_jy"]) & np.isfinite(ph["err_jy"]) & (ph["err_jy"] > 0)]
    ok = ok.assign(w=1.0 / ok["err_jy"] ** 2)
    ok = ok.assign(wf=ok["w"] * ok["flux_jy"])
    g = ok.groupby(["oid", "detector"])
    det = pd.DataFrame({"F": g["wf"].sum() / g["w"].sum(), "E": 1.0 / np.sqrt(g["w"].sum()),
                        "n": g.size(), "lam": g["lambda_um"].median()}).reset_index()
    det["S"] = det["F"] / det["E"]
    wide = det.pivot(index="oid", columns="detector", values=["F", "E", "S", "n", "lam"])
    oids = pd.Index(sorted(ph["oid"].unique()), name="oid")
    t = pd.DataFrame(index=oids)
    for d in range(1, 7):
        for k, name in (("F", "flux"), ("E", "err"), ("S", "snr"), ("n", "nexp"), ("lam", "lambda")):
            col = (k, d)
            t[f"spx_{name}_D{d}"] = wide[col].reindex(oids) if col in wide.columns else np.nan
    t = t.apply(pd.to_numeric, errors="coerce").astype(float)
    for name, a, b in PARES:
        fa, fb = t[f"spx_flux_D{a}"], t[f"spx_flux_D{b}"]
        sa, sb = t[f"spx_snr_D{a}"], t[f"spx_snr_D{b}"]
        good = (sa >= snr_color) & (sb >= snr_color) & (fa > 0) & (fb > 0)
        t[f"spx_{name}"] = np.where(good, -2.5 * np.log10(fa.where(good) / fb.where(good)), np.nan)
    f4, f5, s4, s5, e4 = (t["spx_flux_D4"], t["spx_flux_D5"], t["spx_snr_D4"], t["spx_snr_D5"], t["spx_err_D4"])
    both = (s5 >= snr_color) & (s4 >= snr_color) & (f4 > 0) & (f5 > 0)
    lower = (s5 >= snr_color) & ~(s4 >= snr_color) & (e4 > 0) & (f5 > 0)
    ch4 = np.full(len(t), np.nan)
    ch4[both.to_numpy()] = np.log10((f5 / f4)[both]).to_numpy()
    ch4[lower.to_numpy()] = np.log10((f5 / (3 * e4))[lower]).to_numpy()
    t["spx_ch4"] = ch4
    t["spx_ch4_limite"] = lower.astype(int)
    snrs = t[[f"spx_snr_D{d}" for d in range(1, 7)]]
    t["spx_snr_max"] = snrs.max(axis=1)
    t["spx_n_det"] = (snrs >= snr_det).sum(axis=1)
    t["spx_n_ok"] = ok.groupby("oid").size().reindex(oids).fillna(0).astype(int)
    return t.reset_index()


def run(cfg: dict, log) -> dict:
    sx = cfg["spherex"]
    src = Path(cfg["rutas"]["salidas"]) / "2_fotometria_spherex" / "fotometria.parquet"
    sel = pd.read_parquet(Path(cfg["rutas"]["salidas"]) / "1_indice_spherex" / "seleccion.parquet")
    out = out_dir(cfg, "3_features_spherex")
    ph = pd.read_parquet(src)
    t = agregar(ph, float(sx["snr_color_min"]), float(sx["snr_deteccion"]))
    # objetos seleccionados sin ninguna medición también quedan (todo faltante): son parte de la población
    t = sel[["oid", "label", "control"]].merge(t, on="oid", how="left")
    t["spx_n_ok"] = t["spx_n_ok"].fillna(0).astype(int)
    t["spx_n_det"] = t["spx_n_det"].fillna(0).astype(int)
    ctrl = t[t["control"]].copy()
    train = t[~t["control"]].drop(columns=["control"])
    save_parquet(train, out / "features_spherex.parquet")
    ctrl.to_csv(out / "controles_pilotos.csv", index=False)
    write_json(out / "grupos_spherex.json", GRUPOS)
    cov = train.groupby("label")[GRUPOS["spherex_color"]].apply(lambda x: x.notna().mean()).round(3)
    resumen = {"objetos": int(len(train)), "con_alguna_medicion_ok": int((train["spx_n_ok"] > 0).sum()),
               "cobertura_colores_por_clase": cov.to_dict(orient="index"),
               "controles": ctrl[["oid", "label", "spx_c54", "spx_c65", "spx_ch4", "spx_n_det"]].to_dict(orient="records")}
    write_json(out / "resumen.json", resumen)
    avisos = []
    if resumen["con_alguna_medicion_ok"] < 0.5 * max(len(train), 1):
        avisos.append("menos de la mitad de los objetos tiene alguna medición OK: revisar 2_fotometria_spherex")
    return {"resumen": {k: v for k, v in resumen.items() if k != "controles"}, "avisos": avisos}
