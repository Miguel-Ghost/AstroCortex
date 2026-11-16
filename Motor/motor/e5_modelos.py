"""Etapa 5 · Comparación Random Forest vs XGBoost vs red neuronal, con la partición espacial de TY_PIPELINE.

Por experimento (lista en config `experimentos`):
1. Población y columnas: `todos` (11 850 objetos) o `spherex` (solo los objetos medidos en las etapas 1–3).
   Las columnas salen de 4_preprocesamiento/variables.json.
2. Validación: los 5 pliegues espaciales de desarrollo (celdas de cielo enteras; ningún objeto de una celda
   de validación se ve al entrenar). El test externo (20 % de las celdas) se usa una sola vez, al final.
3. Por modelo se elige la potencia del peso de clase con la mayor macro-F1 fuera de pliegue.
4. Se elige el modelo del experimento con la regla escrita en config (`regla_eleccion`) ANTES de mirar el test.
5. Importancia por permutación (variables sueltas y grupos de TY_PIPELINE) con los modelos de cada pliegue.
6. Modelo final por tipo: se entrena con todo desarrollo y se evalúa en test (todos se informan; la elección ya
   está hecha). Umbral de la clase fría para "unknown" desde las predicciones fuera de pliegue.

Salidas (salidas/5_modelos/<experimento>/): comparacion.csv, metricas.json, oof.parquet, test.parquet,
importancia_variables.csv, importancia_grupos.csv, confusion_*.png, modelo_<tipo>.joblib|.pt
Y salidas/5_modelos/comparacion_global.csv con todas las filas.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import modelos as M
from .comun import out_dir, read_json, save_parquet, write_json

TIPOS = ("rf", "xgb", "mlp")
ORDEN_CLASES = {"5clases": ["star", "M", "L", "T", "Y"], "servible": ["star", "cold_brown_dwarf"]}
POSITIVAS = {"5clases": ["T", "Y"], "servible": ["cold_brown_dwarf"]}


def preparar(cfg: dict, exp: dict, tabla: pd.DataFrame, variables: dict, con_spherex: bool):
    conj = cfg["conjuntos"][exp["conjunto"]]
    pob = exp["poblacion"]
    if conj.get("spherex") and not con_spherex and pob != "spherex_o_todos":
        return None, "requiere variables SPHEREx (etapas 1-3)"
    if pob == "spherex" and not con_spherex:
        return None, "requiere variables SPHEREx (etapas 1-3)"
    cols = list(variables["conjuntos"][exp["conjunto"]])
    if not con_spherex:
        cols = [c for c in cols if not c.startswith("spx_")]
    t = tabla
    if pob == "spherex" or (pob == "spherex_o_todos" and con_spherex):
        t = tabla[tabla["in_spherex"]]
    mapping = cfg["objetivos"][exp["objetivo"]]
    clases = ORDEN_CLASES.get(exp["objetivo"]) or sorted(set(mapping.values()))
    t = t.assign(_y=t["label"].map(mapping)).dropna(subset=["_y"])
    t = t[t["_y"].isin(clases)].reset_index(drop=True)
    cols = [c for c in cols if c in t.columns and t.loc[t["role"] == "dev", c].notna().any()]
    return {"t": t, "cols": cols, "clases": clases, "positivas": POSITIVAS.get(exp["objetivo"], []),
            "poblacion": "spherex" if len(t) < len(tabla) else "todos"}, None


def ajustar(tipo: str, Xtr, ytr, potencia: float, cfg_m: dict, seed: int, k: int, Xva_es=None, yva_es=None):
    wc = M.pesos_clase(ytr, k, potencia)
    if tipo == "rf":
        return M.ajustar_rf(Xtr, ytr, wc[ytr], cfg_m, seed)
    if tipo == "xgb":
        return M.ajustar_xgb(Xtr, ytr, wc[ytr], cfg_m, seed, k)
    return M.ajustar_mlp(Xtr, ytr, wc, Xva_es, yva_es, cfg_m, seed, k)


def predecir(tipo: str, model, X, k: int):
    return M.proba_mlp(model, X) if tipo == "mlp" else M.proba_sklearn(model, X, k)


def cv(tipo, X, y, folds, potencia, cfg_m, seed, k, keep_models=False):
    """OOF con imputación por pliegue. La red usa otro pliegue de desarrollo para la parada temprana."""
    oof = np.full((len(X), k), np.nan)
    modelos = []
    fold_ids = sorted(np.unique(folds))
    for f in fold_ids:
        tr, va = folds != f, folds == f
        med = M.medianas(X[tr])
        Xtr, ytr = M.imputar(X[tr], med), y[tr]
        es = None
        if tipo == "mlp":
            inner = fold_ids[(fold_ids.index(f) + 1) % len(fold_ids)]
            es_mask = folds[tr] == inner
            Xes, yes = Xtr[es_mask], ytr[es_mask]
            Xtr, ytr = Xtr[~es_mask], ytr[~es_mask]
            es = (Xes, yes)
        m = ajustar(tipo, Xtr, ytr, potencia, cfg_m, seed + int(f), k, *(es or (None, None)))
        Xva = M.imputar(X[va], med)
        oof[va] = predecir(tipo, m, Xva, k)
        if keep_models:
            modelos.append((f, m, med))
    return oof, modelos


def permutacion(tipo, modelos, X, y, folds, cols, grupos: dict, clases, positivas, k, reps, seed):
    rng = np.random.default_rng(seed)
    base_scores, ind, grp = [], {c: [] for c in cols}, {g: [] for g in grupos}
    for f, m, med in modelos:
        va = folds == f
        Xva, yva = M.imputar(X[va], med), y[va]
        base = M.metricas(yva, predecir(tipo, m, Xva, k), clases, positivas)["macro_f1"]
        base_scores.append(base)
        for j, c in enumerate(cols):
            for _ in range(reps):
                Xp = Xva.copy()
                Xp[:, j] = rng.permutation(Xp[:, j])
                ind[c].append(base - M.metricas(yva, predecir(tipo, m, Xp, k), clases, positivas)["macro_f1"])
        for g, gcols in grupos.items():
            idx = [cols.index(c) for c in gcols if c in cols]
            if not idx:
                continue
            for _ in range(reps):
                Xp = Xva.copy()
                perm = rng.permutation(len(Xp))
                Xp[:, idx] = Xp[perm][:, idx]
                grp[g].append(base - M.metricas(yva, predecir(tipo, m, Xp, k), clases, positivas)["macro_f1"])
    fi = pd.DataFrame([{"variable": c, "caida_macro_f1": np.mean(v), "desv": np.std(v)} for c, v in ind.items()])
    fg = pd.DataFrame([{"grupo": g, "variables": "+".join(c for c in grupos[g] if c in cols),
                        "caida_macro_f1": np.mean(v), "desv": np.std(v)} for g, v in grp.items() if v])
    return fi.sort_values("caida_macro_f1", ascending=False), fg.sort_values("caida_macro_f1", ascending=False)


def umbral_fria(y, proba, clases, clase, objetivo):
    """Menor umbral (≥ 0.5) tal que la precisión de la clase fría fuera de pliegue sea ≥ objetivo.
    El backend etiqueta la clase ganadora solo si su probabilidad ≥ umbral; si no, 'unknown' (a revisión).
    Con dos clases la ganadora siempre tiene ≥ 0.5, así que un umbral menor no cambiaría nada."""
    if clase not in clases:
        return None, None
    j = clases.index(clase)
    p, is_c = proba[:, j], (y == j)
    for tau in np.round(np.arange(0.50, 0.96, 0.01), 2):
        sel = p >= tau
        if sel.sum() >= 5 and is_c[sel].mean() >= objetivo:
            return float(tau), {"precision": float(is_c[sel].mean()), "recall": float(sel[is_c].mean()),
                                "cobertura": float(sel.mean())}
    return 0.5, None


def plot_confusion(m: dict, path: Path, titulo: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cm = np.array(m["confusion"], float)
    labs = m["confusion_etiquetas"]
    norm = cm / np.maximum(cm.sum(axis=1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(1.2 * len(labs) + 2, 1.1 * len(labs) + 1.5), dpi=110)
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    for i in range(len(labs)):
        for j in range(len(labs)):
            ax.text(j, i, f"{int(cm[i, j])}\n{norm[i, j]:.0%}", ha="center", va="center",
                    color="white" if norm[i, j] > 0.6 else "black", fontsize=8)
    ax.set_xticks(range(len(labs)), labs)
    ax.set_yticks(range(len(labs)), labs)
    ax.set_xlabel("predicha")
    ax.set_ylabel("real")
    ax.set_title(titulo, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def guardar_modelo(tipo, model, med, cols, clases, potencia, path_base: Path, extra: dict):
    meta = {"tipo": tipo, "columnas": cols, "medianas": med.tolist(), "clases": clases, "potencia_peso": potencia, **extra}
    if tipo == "mlp":
        import torch
        n_in = len(cols)
        torch.save({"state_dict": model.state_dict(), "n_in": n_in, "n_out": len(clases),
                    "capas": extra["mlp"]["capas"], "dropout": extra["mlp"]["dropout"], "meta": meta},
                   path_base.with_suffix(".pt"))
        return path_base.with_suffix(".pt")
    import joblib
    joblib.dump({"modelo": model, "meta": meta}, path_base.with_suffix(".joblib"))
    return path_base.with_suffix(".joblib")


def run(cfg: dict, log) -> dict:
    cm = cfg["modelos"]
    seed = int(cfg["semilla"])
    src = Path(cfg["rutas"]["salidas"]) / "4_preprocesamiento"
    tabla = pd.read_parquet(src / "tabla_modelo.parquet")
    variables = read_json(src / "variables.json")
    con_spherex = bool(tabla["in_spherex"].any())
    grupos = {g: c for g, c in variables["grupos_ty"].items() if not g.startswith("AUDIT")}
    if variables.get("grupos_spherex"):
        grupos["spherex_color"] = variables["grupos_spherex"]["spherex_color"]
    base = out_dir(cfg, "5_modelos")
    filas, resumen, avisos = [], {}, []
    for exp in cfg["experimentos"]:
        name = exp["nombre"]
        prep, motivo = preparar(cfg, exp, tabla, variables, con_spherex)
        if prep is None:
            resumen[name] = {"estado": "OMITIDO", "motivo": motivo}
            log.info("%s: omitido (%s)", name, motivo)
            continue
        out = out_dir(cfg, "5_modelos", name)
        t, cols, clases, positivas = prep["t"], prep["cols"], prep["clases"], prep["positivas"]
        k = len(clases)
        dev = t[t["role"] == "dev"].reset_index(drop=True)
        test = t[t["role"] == "test"].reset_index(drop=True)
        Xd = dev[cols].to_numpy(np.float64)
        yd = dev["_y"].map({c: i for i, c in enumerate(clases)}).to_numpy(int)
        Xt = test[cols].to_numpy(np.float64)
        yt = test["_y"].map({c: i for i, c in enumerate(clases)}).to_numpy(int)
        folds = dev["cv_fold"].to_numpy(int)
        log.info("== %s: %d variables, dev %d, test %d, clases %s", name, len(cols), len(dev), len(test),
                 dict(zip(clases, np.bincount(yd, minlength=k).tolist())))
        res_exp = {"variables": cols, "poblacion": prep["poblacion"], "clases": clases,
                   "n_dev": int(len(dev)), "n_test": int(len(test)), "modelos": {}}
        oof_best = {}
        for tipo in TIPOS:
            t0 = time.monotonic()
            por_pot = {}
            for pw in cm["potencias_peso_clase"]:
                oof, _ = cv(tipo, Xd, yd, folds, float(pw), cm, seed, k)
                por_pot[str(pw)] = (M.metricas(yd, oof, clases, positivas), oof)
            best_pw = max(por_pot, key=lambda p: por_pot[p][0]["macro_f1"])
            m_cv, oof = por_pot[best_pw]
            oof_best[tipo] = (oof, float(best_pw))
            res_exp["modelos"][tipo] = {"potencia_elegida": float(best_pw),
                                        "cv_por_potencia": {p: M.resumen_corto(v[0], clases) for p, v in por_pot.items()},
                                        "cv": m_cv, "segundos_cv": round(time.monotonic() - t0, 1)}
            log.info("%s %s: potencia %s, CV %s (%.0f s)", name, tipo, best_pw, M.resumen_corto(m_cv, clases),
                     time.monotonic() - t0)
        elegido = max(TIPOS, key=lambda tp: res_exp["modelos"][tp]["cv"]["macro_f1"])
        res_exp["elegido"] = elegido
        res_exp["regla"] = cm["regla_eleccion"]

        # importancia por permutación y modelos finales (todos los tipos, test una vez)
        pos_idx = [clases.index(c) for c in positivas if c in clases]
        oof_df = pd.DataFrame({"oid": dev["oid"], "label": dev["label"], "y": dev["_y"], "cv_fold": folds})
        test_df = pd.DataFrame({"oid": test["oid"], "label": test["label"], "y": test["_y"]})
        for tipo in TIPOS:
            oof, pw = oof_best[tipo]
            for j, c in enumerate(clases):
                oof_df[f"p_{tipo}_{c}"] = oof[:, j]
            _, fold_models = cv(tipo, Xd, yd, folds, pw, cm, seed, k, keep_models=True)
            fi, fg = permutacion(tipo, fold_models, Xd, yd, folds, cols,
                                 {g: c for g, c in grupos.items() if any(x in cols for x in c)},
                                 clases, positivas, k, int(cm["permutaciones"]), seed)
            fi.to_csv(out / f"importancia_variables_{tipo}.csv", index=False)
            fg.to_csv(out / f"importancia_grupos_{tipo}.csv", index=False)
            med = M.medianas(Xd)
            Xdi = M.imputar(Xd, med)
            es = None
            if tipo == "mlp":
                f0 = sorted(np.unique(folds))[0]
                es = (Xdi[folds == f0], yd[folds == f0])
                final = ajustar(tipo, Xdi[folds != f0], yd[folds != f0], pw, cm, seed, k, *es)
            else:
                final = ajustar(tipo, Xdi, yd, pw, cm, seed, k)
            pt = predecir(tipo, final, M.imputar(Xt, med), k)
            for j, c in enumerate(clases):
                test_df[f"p_{tipo}_{c}"] = pt[:, j]
            m_test = M.metricas(yt, pt, clases, positivas)
            m_test["ic95_recall_positivas"] = M.ic_recall(yt, np.argmax(pt, axis=1), pos_idx, seed=seed)
            res_exp["modelos"][tipo]["test"] = m_test
            res_exp["modelos"][tipo]["importancia_top"] = fi.head(8)[["variable", "caida_macro_f1"]].to_dict("records")
            res_exp["modelos"][tipo]["importancia_grupos"] = fg[["grupo", "caida_macro_f1"]].to_dict("records")
            tau, tau_info = (umbral_fria(yd, oof, clases, cfg["exportar"]["clase_fria"], float(cm["precision_objetivo_fria"]))
                             if exp["objetivo"] == "servible" else (None, None))
            res_exp["modelos"][tipo]["umbral_clase_fria"] = {"tau": tau, "oof": tau_info}
            path = guardar_modelo(tipo, final, med, cols, clases, pw, out / f"modelo_{tipo}",
                                  {"experimento": name, "mlp": cm["mlp"], "umbral_clase_fria": tau,
                                   "cv": M.resumen_corto(res_exp["modelos"][tipo]["cv"], clases),
                                   "test": M.resumen_corto(m_test, clases)})
            res_exp["modelos"][tipo]["archivo"] = path.name
            plot_confusion(res_exp["modelos"][tipo]["cv"], out / f"confusion_cv_{tipo}.png", f"{name} · {tipo} · CV")
            plot_confusion(m_test, out / f"confusion_test_{tipo}.png", f"{name} · {tipo} · test")
            filas.append({"experimento": name, "modelo": tipo, "elegido_por_cv": tipo == elegido,
                          "potencia_peso": pw, "n_variables": len(cols), "poblacion": prep["poblacion"],
                          **{f"cv_{a}": b for a, b in M.resumen_corto(res_exp["modelos"][tipo]["cv"], clases).items()},
                          **{f"test_{a}": b for a, b in M.resumen_corto(m_test, clases).items()}})
        save_parquet(oof_df, out / "oof.parquet")
        save_parquet(test_df, out / "test.parquet")
        pd.DataFrame([f for f in filas if f["experimento"] == name]).to_csv(out / "comparacion.csv", index=False)
        write_json(out / "metricas.json", res_exp)
        resumen[name] = {"estado": "OK", "elegido": elegido, "n_variables": len(cols), "poblacion": prep["poblacion"],
                         "cv_macro_f1": {tp: round(res_exp["modelos"][tp]["cv"]["macro_f1"], 4) for tp in TIPOS},
                         "test_elegido": M.resumen_corto(res_exp["modelos"][elegido]["test"], clases)}
        log.info("%s: elegido %s → test %s", name, elegido, resumen[name]["test_elegido"])
    pd.DataFrame(filas).to_csv(base / "comparacion_global.csv", index=False)
    write_json(base / "resumen.json", resumen)
    if not con_spherex:
        avisos.append("sin variables SPHEREx: los experimentos C y D se omitieron y E usa solo catálogo")
    return {"resumen": resumen, "avisos": avisos}
