"""Etapa 4 · Preprocesamiento: duplicados, valores imposibles, faltantes, outliers y balance de clases.

Reglas (fijadas antes de mirar el test; ver LEEME, sección "Decisiones"):
- Duplicados
  * oid repetido: error (no debería pasar).
  * Mismo objeto físico con dos oid: posiciones propagadas a 2016.0 a menos de `radio_duplicado_arcsec`.
    Si comparten etiqueta se conserva el oid menor; si las etiquetas difieren se quitan todos (etiqueta dudosa).
  * Filas con el mismo vector de variables físicas (≥5 valores) en oid distintos: mismo criterio.
- Valores imposibles → faltante: colores con |valor| > `limite_fisico_color_mag`; μ CatWISE > 20″/año
  (la estrella de Barnard, la más rápida conocida, tiene 10.4″/año).
- Faltantes: NO se imputan aquí. Se imputan dentro de cada pliegue con la mediana del entrenamiento
  (etapa 5) y esa mediana viaja al backend en metadata.json. No se agregan indicadores de "falta":
  en esta muestra la ausencia de un catálogo delata cómo se armó la tabla (experimento E0 de TY_PIPELINE).
  Se quitan variables con más de `max_faltante_dev` de faltantes en desarrollo.
- Outliers: se cuentan por clase con z robusto (mediana/MAD) > `outlier_mad_k` y se informan.
  No se borran: un extremo de color puede ser justo una enana Y. La red neuronal recorta a los
  percentiles 0.5–99.5 del entrenamiento dentro de su propio grafo (viaja en el ONNX).
- Balance: no se remuestrea. Se usan pesos por clase (N / (K·n_c))^p con p elegido por CV en la etapa 5.
  SMOTE no: con 50 Y inventaría vecinos de pocos puntos.

Salidas (salidas/4_preprocesamiento/): tabla_modelo.parquet, variables.json, duplicados.csv,
faltantes_por_clase.csv, outliers_por_clase.csv, balance.json, preprocesamiento.json
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .comun import out_dir, read_json, save_parquet, ty_run_dir, write_json
from .spherex_io import propagate

NO_COLOR = {"cw_mu", "cw_log_mu", "Hrpm_W2", "Hrpm_J", "Hrpm_W2_pm", "cw_mu_snr", "W3_detectada",
            "aw_var_w2", "cw_par", "cw_par_snr", "gaia_parallax", "gaia_plx_snr", "gaia_ruwe", "gaia_Cstar",
            "gaia_mu", "gaia_M_W2"}


def expand(groups: dict, names: list[str]) -> list[str]:
    out = []
    for g in names:
        out += [c for c in groups.get(g, []) if c not in out]
    return out


def variables_por_conjunto(cfg: dict, ty_groups: dict, ty_sets: dict, spx_groups: dict | None) -> dict:
    res = {}
    for name, spec in cfg["conjuntos"].items():
        cols = expand(ty_groups, ty_sets[spec["conjunto_ty"]]) if "conjunto_ty" in spec else list(spec["variables"])
        if spec.get("spherex") and spx_groups:
            cols += [c for c in spx_groups["spherex_color"] if c not in cols]
        res[name] = cols
    return res


def duplicados_posicion(obj: pd.DataFrame, radius: float, epoch: float) -> list[list[int]]:
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    ra, dec = [], []
    for r in obj.itertuples(index=False):
        a, d = propagate(r.ra, r.dec, r.pmra, r.pmdec, float(r.epoch), epoch)
        ra.append(a)
        dec.append(d)
    ra, dec = np.radians(ra), np.radians(dec)
    xyz = np.c_[np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)]
    chord = 2 * np.sin(np.radians(radius / 3600.0) / 2)
    pairs = cKDTree(xyz).query_pairs(chord, output_type="ndarray")
    if len(pairs) == 0:
        return []
    n = len(obj)
    g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    _, comp = connected_components(g, directed=False)
    groups = pd.Series(np.arange(n)).groupby(comp).apply(list)
    return [v for v in groups if len(v) > 1]


def run(cfg: dict, log) -> dict:
    pp = cfg["preprocesamiento"]
    out = out_dir(cfg, "4_preprocesamiento")
    tyd = ty_run_dir(cfg)
    feat = pd.read_parquet(tyd / "01_variables" / "features.parquet")
    part = pd.read_parquet(tyd / "02_particion" / "particion.parquet")
    meta = read_json(tyd / "01_variables" / "feature_groups.json")
    obj = pd.read_parquet(Path(cfg["rutas"]["datos_entrada"]) / "processed" / "objects.parquet")
    log.info("TY_PIPELINE usado: %s", tyd)

    spx_path = Path(cfg["rutas"]["salidas"]) / "3_features_spherex" / "features_spherex.parquet"
    spx, spx_groups = None, None
    if spx_path.is_file():
        spx = pd.read_parquet(spx_path)
        spx_groups = read_json(spx_path.with_name("grupos_spherex.json"))
        log.info("variables SPHEREx: %d objetos", len(spx))
    else:
        log.info("sin variables SPHEREx (etapas 1-3 no ejecutadas): solo catálogo")

    t = feat.merge(part[["oid", "role", "cv_fold", "sky_cell"]], on="oid", how="inner", validate="one_to_one")
    if t["oid"].duplicated().any():
        raise RuntimeError("oid duplicado en la tabla de variables")
    t["in_spherex"] = False
    if spx is not None:
        keep = [c for c in spx.columns if c.startswith("spx_")]
        t = t.merge(spx[["oid"] + keep], on="oid", how="left", validate="one_to_one")
        t["in_spherex"] = t["oid"].isin(spx["oid"])
    sets = variables_por_conjunto(cfg, meta["groups"], meta["feature_sets"], spx_groups)
    candidatas = []
    for cols in sets.values():
        candidatas += [c for c in cols if c not in candidatas and c in t.columns]
    faltan = sorted({c for cols in sets.values() for c in cols if c not in t.columns})
    n0 = len(t)

    # ---------------- duplicados ----------------
    dup_rows = []
    o = obj.set_index("oid").loc[t["oid"], ["label", "ra", "dec", "pmra", "pmdec", "epoch"]].reset_index()
    for comp in duplicados_posicion(o, float(pp["radio_duplicado_arcsec"]), float(pp["epoca_comun_duplicados"])):
        sub = o.iloc[comp]
        same = sub["label"].nunique() == 1
        keep_oid = int(sub["oid"].min()) if same else None
        for r in sub.itertuples(index=False):
            dup_rows.append({"tipo": "posicion", "grupo": int(sub["oid"].min()), "oid": int(r.oid), "label": r.label,
                             "accion": "conservar" if r.oid == keep_oid else ("quitar_duplicado" if same else "quitar_etiqueta_en_conflicto")})
    phys = [c for c in sets.get("catalogo", candidatas) if c in t.columns]
    filled = t[phys].notna().sum(axis=1) >= 5
    key = pd.util.hash_pandas_object(t.loc[filled, phys].apply(pd.to_numeric, errors="coerce")
                                     .round(6).fillna(-9.9e9), index=False)
    for _, g in t.loc[filled].groupby(key):
        if len(g) < 2:
            continue
        same = g["label"].nunique() == 1
        keep_oid = int(g["oid"].min()) if same else None
        for r in g.itertuples(index=False):
            dup_rows.append({"tipo": "vector_identico", "grupo": int(g["oid"].min()), "oid": int(r.oid), "label": r.label,
                             "accion": "conservar" if r.oid == keep_oid else ("quitar_duplicado" if same else "quitar_etiqueta_en_conflicto")})
    dups = pd.DataFrame(dup_rows, columns=["tipo", "grupo", "oid", "label", "accion"])
    dups.to_csv(out / "duplicados.csv", index=False)
    quitar = set(dups.loc[dups["accion"] != "conservar", "oid"].astype(int))
    t = t[~t["oid"].isin(quitar)].reset_index(drop=True)
    log.info("duplicados: %d grupos, %d filas quitadas", dups["grupo"].nunique() if len(dups) else 0, len(quitar))

    # ---------------- valores imposibles ----------------
    imposibles = {}
    lim = float(pp["limite_fisico_color_mag"])
    for c in candidatas:
        x = pd.to_numeric(t[c], errors="coerce").replace([np.inf, -np.inf], np.nan)
        if c in NO_COLOR or c.startswith("spx_n") or c.endswith("_limite"):
            bad = pd.Series(False, index=t.index)
            if c == "cw_mu":
                bad = x > 20.0
        else:
            bad = x.abs() > lim
        imposibles[c] = int(bad.sum())
        t[c] = x.mask(bad)

    # ---------------- faltantes ----------------
    dev = t[t["role"] == "dev"]
    falt = dev.groupby("label")[candidatas].apply(lambda x: x.isna().mean()).T.round(4)
    falt["total_dev"] = dev[candidatas].isna().mean().round(4)
    falt.to_csv(out / "faltantes_por_clase.csv", index_label="variable")
    sin_uso = [c for c in candidatas if falt.loc[c, "total_dev"] > float(pp["max_faltante_dev"])]
    for name in sets:
        sets[name] = [c for c in sets[name] if c in t.columns and c not in sin_uso]

    # ---------------- outliers (se informan, no se borran) ----------------
    k = float(pp["outlier_mad_k"])
    rows = []
    for c in candidatas:
        for lab, g in dev.groupby("label"):
            x = pd.to_numeric(g[c], errors="coerce").dropna()
            if len(x) < 10:
                continue
            med = x.median()
            mad = (x - med).abs().median() * 1.4826
            n_out = int(((x - med).abs() > k * mad).sum()) if mad > 0 else 0
            rows.append({"variable": c, "clase": lab, "n": len(x), "mediana": med, "mad": mad, "n_outlier": n_out,
                         "frac_outlier": n_out / len(x)})
    outl = pd.DataFrame(rows)
    outl.to_csv(out / "outliers_por_clase.csv", index=False)

    # ---------------- balance ----------------
    balance = {}
    for oname, mapping in cfg["objetivos"].items():
        y = t["label"].map(mapping)
        balance[oname] = {r: y[t["role"] == r].value_counts().to_dict() for r in ("dev", "test")}
        if spx is not None:
            balance[oname]["dev_subconjunto_spherex"] = y[(t["role"] == "dev") & t["in_spherex"]].value_counts().to_dict()
    write_json(out / "balance.json", {"conteos": balance,
                                      "estrategia": "pesos por clase (N/(K·n_c))^p, p elegido por CV entre "
                                                    f"{cfg['modelos']['potencias_peso_clase']}; sin remuestreo ni SMOTE"})

    base_cols = ["oid", "label", "role", "cv_fold", "sky_cell", "in_spherex"]
    audit = [c for c in (spx_groups or {}).get("AUDIT_spherex", []) if c in t.columns]
    tabla = t[base_cols + [c for c in candidatas if c not in sin_uso] + audit]
    save_parquet(tabla, out / "tabla_modelo.parquet")
    write_json(out / "variables.json", {"conjuntos": sets, "grupos_ty": meta["groups"],
                                        "grupos_spherex": spx_groups, "auditoria_no_predictor": audit,
                                        "quitadas_por_faltantes": sin_uso, "no_encontradas": faltan})
    resumen = {"filas_inicio": n0, "filas_final": int(len(tabla)), "quitadas_duplicado": len(quitar),
               "valores_imposibles_a_faltante": {k2: v for k2, v in imposibles.items() if v},
               "variables_quitadas_por_faltantes": sin_uso,
               "variables_por_conjunto": {k2: len(v) for k2, v in sets.items()},
               "outliers_marcados_total": int(outl["n_outlier"].sum()) if len(outl) else 0,
               "con_spherex": bool(spx is not None), "ty_run": str(tyd)}
    write_json(out / "preprocesamiento.json", resumen)
    avisos = [f"variables pedidas que no existen: {faltan}"] if faltan else []
    return {"resumen": resumen, "avisos": avisos}
