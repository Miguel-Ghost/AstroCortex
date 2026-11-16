"""Etapa 5: experimentos, modelo robusto frente a la dependencia de una sola variable,
umbral de 'desconocido' y evaluación ÚNICA en el test espacial externo.

Pruebas de atajos (lo que el modelo NO debería poder aprovechar):
- E0: solo faltantes, separaciones de cruce, latitud galáctica y brillo.
- E3 vs E1: cuánto gana el modelo al ver el brillo aparente.
- Repesado por brillo: rendimiento cuando estrellas/M/L tienen el mismo W2 que las T/Y.
Prueba de estrés: se apaga cada cluster en validación (como si esa medición faltara)
y se compara el modelo base con el entrenado con apagado aleatorio de grupos.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from .common import sha256, write_json, utc
from .ml import (CLASSES, bootstrap_recall, brightness_weights, cluster_name, correlation_clusters,
                 cv_oof, dropout_augment, fit_model, matrix, metrics, proba_full)
from .s1_features import load_saved
from .s4_importance import expand, usable


def short(m: dict) -> dict:
    return {"bal_acc": round(m["balanced_accuracy"], 4), "macro_f1": round(m["macro_f1"], 4),
            "ap_TY": None if m["ap_TY_vs_resto"] is None else round(m["ap_TY_vs_resto"], 4),
            "recall_T": round(m["por_clase"].get("T", {}).get("recall", float("nan")), 3),
            "recall_Y": round(m["por_clase"].get("Y", {}).get("recall", float("nan")), 3),
            "precision_Y": round(m["por_clase"].get("Y", {}).get("precision", float("nan")), 3),
            "precision_TY": m["TY_binario"]["precision"]}


def choose_threshold(y, proba, target: float):
    pred = np.array(CLASSES)[proba.argmax(1)]
    conf = proba.max(1)
    is_ty = np.isin(y, ["T", "Y"])
    best = None
    for tau in np.round(np.arange(0.30, 0.99, 0.01), 2):
        keep = conf >= tau
        ty_pred = keep & np.isin(pred, ["T", "Y"])
        if ty_pred.sum() < 10:
            continue
        prec = float(is_ty[ty_pred].mean())
        if prec >= target:
            best = {"tau": float(tau), "precision_TY": prec,
                    "recall_TY": float(ty_pred[is_ty].mean()), "cobertura": float(keep.mean())}
            break
    return best


def apply_threshold(proba, tau):
    pred = np.array(CLASSES, dtype=object)[proba.argmax(1)]
    pred[proba.max(1) < tau] = "desconocido"
    return pred


def run(cfg: dict, out: Path, feat_dir: Path, split_dir: Path, imp_dir: Path, log) -> dict:
    t = load_saved(feat_dir / "features")
    split = load_saved(split_dir / "particion")
    meta = json.loads((feat_dir / "feature_groups.json").read_text(encoding="utf-8"))
    groups, sets = meta["groups"], meta["feature_sets"]
    t = t.merge(split[["oid", "role", "cv_fold"]], on="oid")
    dev = t.loc[t["role"] == "dev"].reset_index(drop=True)
    test = t.loc[t["role"] == "test"].reset_index(drop=True)
    y_dev, y_test = dev["label"].to_numpy(), test["label"].to_numpy()
    seed = int(cfg["seed"])
    rb = cfg["robustness"]
    warnings = []

    # ---------- 0. Peso de clases elegido por CV (regla fijada en config) ----------
    # 'balanced' completo (potencia 1) hace que el modelo sobre-prediga Y (50 objetos).
    # Se compara en CV de desarrollo y se elige la mayor macro-F1 (equilibra precisión y recall).
    base_cols = usable(dev, expand(groups, sets["E1_nucleo_fisico"]))
    weight_cmp = {}
    for pw in cfg["model"].get("class_weight_power_candidates", [1.0]):
        cfg["model"]["class_weight_power"] = pw
        weight_cmp[str(pw)] = short(metrics(y_dev, cv_oof(dev, base_cols, cfg, seed)))
        log.info("peso de clase potencia %s: %s", pw, weight_cmp[str(pw)])
    best_pw = max(weight_cmp, key=lambda k: weight_cmp[k]["macro_f1"])
    cfg["model"]["class_weight_power"] = float(best_pw)
    write_json(out / "eleccion_peso_clases.json", {"comparacion_cv": weight_cmp, "elegida": float(best_pw),
                                                   "regla": "max macro-F1 en CV de desarrollo (E1)"})

    # ---------- 1. Experimentos de conjuntos de variables ----------
    exp = {}
    wb = brightness_weights(dev)
    for name, gs in sets.items():
        cols = usable(dev, expand(groups, gs))
        if not cols:
            continue
        oof = cv_oof(dev, cols, cfg, seed)
        m = metrics(y_dev, oof)
        mw = metrics(y_dev, oof, weights=wb)
        exp[name] = {"variables": cols, "cv": short(m), "cv_repesado_por_brillo": short(mw)}
        log.info("experimento %s: %s | repesado %s", name, exp[name]["cv"], exp[name]["cv_repesado_por_brillo"])
    write_json(out / "experimentos.json", exp)
    if "E0_solo_atajos" in exp and exp["E0_solo_atajos"]["cv"]["bal_acc"] > 0.6:
        warnings.append(f"ATAJO: solo faltantes/brillo/posición logran bal_acc "
                        f"{exp['E0_solo_atajos']['cv']['bal_acc']:.2f}; la muestra trae sesgo de construcción")
    if "E3_nucleo_mas_brillo" in exp and "E1_nucleo_fisico" in exp:
        gain = exp["E3_nucleo_mas_brillo"]["cv"]["bal_acc"] - exp["E1_nucleo_fisico"]["cv"]["bal_acc"]
        if gain > 0.02:
            warnings.append(f"ATAJO: añadir brillo aparente sube bal_acc {gain:+.3f}; se excluye del modelo")

    # ---------- 2. Base vs robusto + estrés, para E1 (principal) y E2 ----------
    candidates = {}
    stress_rows = []
    for name in ("E1_nucleo_fisico", "E2_nucleo_mas_gaia"):
        if name not in exp:
            continue
        cols = exp[name]["variables"]
        clusters = correlation_clusters(dev, cols, rb["corr_cluster_threshold"])
        cl_idx = [[cols.index(c) for c in cl] for cl in clusters]
        imp_file = imp_dir / name / "permutacion.csv"
        forced = None
        if imp_file.is_file():
            pc = pd.read_csv(imp_file)
            pc = pc.loc[pc["tipo"] == "cluster"].sort_values("delta_bal_acc_media", ascending=False)
            top = pc.iloc[0]["unidad"] if len(pc) else None
            for cl in clusters:
                if cluster_name(cl) == top:
                    forced = [cols.index(c) for c in cl]

        def aug(X, y, rng, cl_idx=cl_idx, forced=forced):
            return dropout_augment(X, y, cl_idx, rb["dropout_probability"], rb["dropout_copies"], rng, forced)

        variants = {"base": None, "robusto": aug}
        res = {}
        for vname, augment in variants.items():
            clean = metrics(y_dev, cv_oof(dev, cols, cfg, seed, augment=augment))
            per_cluster = {}
            for cl in clusters:
                st = metrics(y_dev, cv_oof(dev, cols, cfg, seed, augment=augment, mask_cols=cl))
                per_cluster[cluster_name(cl)] = st["balanced_accuracy"]
                stress_rows.append({"conjunto": name, "variante": vname, "cluster_apagado": cluster_name(cl),
                                    "bal_acc": st["balanced_accuracy"],
                                    "recall_T": st["por_clase"].get("T", {}).get("recall"),
                                    "recall_Y": st["por_clase"].get("Y", {}).get("recall")})
            worst = min(per_cluster.values()) if per_cluster else clean["balanced_accuracy"]
            res[vname] = {"limpio": short(clean), "peor_caso_estres": worst,
                          "cluster_mas_critico": min(per_cluster, key=per_cluster.get) if per_cluster else None}
        candidates[name] = {"variables": cols, "clusters": clusters, "forced": forced, **res}
        log.info("%s base %s | robusto %s", name, res["base"], res["robusto"])
    pd.DataFrame(stress_rows).to_csv(out / "prueba_estres.csv", index=False)

    # ---------- 3. Elección (prerregistrada en config) ----------
    main = "E1_nucleo_fisico"
    c = candidates[main]
    loss = c["base"]["limpio"]["bal_acc"] - c["robusto"]["limpio"]["bal_acc"]
    use_robust = (c["robusto"]["peor_caso_estres"] > c["base"]["peor_caso_estres"]
                  and loss <= rb["max_clean_loss_for_robust"])
    variant = "robusto" if use_robust else "base"
    cols = c["variables"]
    cl_idx = [[cols.index(x) for x in cl] for cl in c["clusters"]]

    def final_aug(X, y, rng):
        return dropout_augment(X, y, cl_idx, rb["dropout_probability"], rb["dropout_copies"], rng, c["forced"])

    augment = final_aug if use_robust else None
    oof = cv_oof(dev, cols, cfg, seed, augment=augment)
    thr = choose_threshold(y_dev, oof, cfg["abstention"]["target_precision_ty"])
    if thr is None:
        warnings.append("No se alcanza la precisión T/Y objetivo con ningún umbral; se usa 0.5")
        thr = {"tau": 0.5}

    X = matrix(dev, cols)
    Xtr, ytr = (augment(X, y_dev, np.random.default_rng(seed)) if augment else (X, y_dev))
    model = fit_model(cfg, seed, Xtr, ytr)

    # ---------- 4. Test externo: se evalúa UNA vez ----------
    Xte = matrix(test, cols)
    p_test = proba_full(model, Xte)
    m_test = metrics(y_test, p_test)
    pred_test = np.array(CLASSES)[p_test.argmax(1)]
    pred_abst = apply_threshold(p_test, thr["tau"])
    keep = pred_abst != "desconocido"
    test_stress = {}
    for cl in c["clusters"]:
        Xs = Xte.copy()
        Xs[:, [cols.index(x) for x in cl]] = np.nan
        test_stress[cluster_name(cl)] = short(metrics(y_test, proba_full(model, Xs)))
    report = {
        "generated_utc": utc(), "conjunto": main, "variante": variant,
        "regla_eleccion": "robusto si mejora el peor caso de estrés y pierde <= "
                          f"{rb['max_clean_loss_for_robust']} de bal_acc limpia",
        "variables": cols, "umbral_desconocido": thr,
        "potencia_peso_clases": cfg["model"]["class_weight_power"],
        "cv_desarrollo": short(metrics(y_dev, oof)),
        "test_externo": {"limpio": short(m_test), "completo": m_test,
                         "IC95_recall_Y": bootstrap_recall(y_test, pred_test, "Y"),
                         "IC95_recall_T": bootstrap_recall(y_test, pred_test, "T"),
                         "con_desconocido": {
                             "cobertura": float(keep.mean()),
                             "precision_TY_aceptadas": float(np.isin(y_test[keep & np.isin(pred_abst, ["T", "Y"])],
                                                                     ["T", "Y"]).mean())
                             if (keep & np.isin(pred_abst, ["T", "Y"])).any() else None},
                         "estres_por_cluster": test_stress,
                         "repesado_por_brillo": short(metrics(y_test, p_test, weights=brightness_weights(test)))},
        "comparacion_base_vs_robusto_cv": {k: {kk: v[kk] for kk in ("limpio", "peor_caso_estres",
                                                                    "cluster_mas_critico")}
                                           for k, v in ((v, candidates[main][v]) for v in ("base", "robusto"))},
        "E2_con_gaia_cv": {v: candidates.get("E2_nucleo_mas_gaia", {}).get(v, {}).get("limpio")
                           for v in ("base", "robusto")},
    }
    write_json(out / "modelo_final.json", report)
    pred_df = pd.DataFrame({"oid": test["oid"], "label": y_test, "pred": pred_test, "pred_con_umbral": pred_abst,
                            **{f"p_{k}": p_test[:, i] for i, k in enumerate(CLASSES)}})
    pred_df.to_csv(out / "predicciones_test.csv", index=False)
    with (out / "modelo_final.pkl").open("wb") as fh:
        pickle.dump({"model": model, "features": cols, "classes": CLASSES, "tau": thr["tau"],
                     "variant": variant}, fh)
    write_json(out / "modelo_final_meta.json", {"pkl_sha256": sha256(out / "modelo_final.pkl"),
                                                "features": cols, "classes": CLASSES, "tau": thr["tau"],
                                                "uso": "p = model.predict_proba(X[features]); "
                                                       "clase 'desconocido' si max(p) < tau"})
    plot_confusion(m_test, out / "confusion_test.png")
    summary = {"variante": variant, "cv": report["cv_desarrollo"], "test": report["test_externo"]["limpio"],
               "tau": thr["tau"], "cobertura_test": report["test_externo"]["con_desconocido"]["cobertura"],
               "IC95_recall_Y": report["test_externo"]["IC95_recall_Y"]}
    return {"summary": summary, "warnings": warnings}


def plot_confusion(m: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cm = np.array(m["confusion"], float)
    norm = cm / np.maximum(cm.sum(1, keepdims=True), 1)
    labels = m["confusion_labels"]
    fig, ax = plt.subplots(figsize=(5, 4.3))
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, f"{int(cm[i, j])}\n{norm[i, j]:.2f}", ha="center", va="center", fontsize=7)
    ax.set_xticks(range(len(labels)), labels)
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlabel("predicha")
    ax.set_ylabel("verdadera")
    ax.set_title("Test espacial externo")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
