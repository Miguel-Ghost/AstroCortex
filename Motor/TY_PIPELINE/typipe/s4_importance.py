"""Etapa 4: importancia de variables mixta y diagnóstico de dependencia de una sola variable.

Métodos (todos con validación cruzada espacial, solo conjunto de desarrollo):
1. Clusters de variables correlacionadas (|Spearman| >= umbral).
2. Permutación POR CLUSTER (se permutan juntas las variables relacionadas;
   permutar una sola subestima su papel porque su gemela la reemplaza).
3. Permutación individual.
4. Ablación: reentrenar sin cada cluster (mide si el modelo tiene respaldo).
5. Información mutua.
6. Boruta (implementación propia con variables sombra y prueba binomial).
7. Cuota de dominancia: fracción de la importancia que se lleva el cluster principal.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import mutual_info_classif
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

from .common import write_json
from .ml import CLASSES, cluster_name, correlation_clusters, cv_oof, fit_model, matrix, metrics, proba_full
from .s1_features import load_saved


def expand(groups: dict, set_groups: list[str]) -> list[str]:
    return list(dict.fromkeys(c for g in set_groups for c in groups[g]))


def usable(dev: pd.DataFrame, cols: list[str]) -> list[str]:
    keep = []
    for c in cols:
        x = pd.to_numeric(dev[c], errors="coerce")
        if x.notna().sum() >= 30 and x.nunique() > 1:
            keep.append(c)
    return keep


def permutation_by_groups(dev, cols, clusters, cfg, seed):
    X = matrix(dev, cols)
    y = dev["label"].to_numpy()
    folds = dev["cv_fold"].to_numpy()
    reps = int(cfg["importance"]["permutation_repeats"])
    rng = np.random.default_rng(seed)
    units = [("cluster", cl) for cl in clusters] + [("variable", [c]) for c in cols]
    drops = {i: [] for i in range(len(units))}
    for k in sorted(np.unique(folds)):
        tr, va = folds != k, folds == k
        model = fit_model(cfg, seed + int(k), X[tr], y[tr])
        Xva, yva = X[va], y[va]
        base = balanced_accuracy_score(yva, np.array(CLASSES)[proba_full(model, Xva).argmax(1)])
        for i, (_, members) in enumerate(units):
            idx = [cols.index(c) for c in members]
            for _ in range(reps):
                Xp = Xva.copy()
                perm = rng.permutation(len(Xp))
                Xp[:, idx] = Xp[perm][:, idx]
                score = balanced_accuracy_score(yva, np.array(CLASSES)[proba_full(model, Xp).argmax(1)])
                drops[i].append(base - score)
    rows = []
    for i, (kind, members) in enumerate(units):
        d = np.array(drops[i])
        rows.append({"tipo": kind, "unidad": cluster_name(members), "variables": members,
                     "delta_bal_acc_media": float(d.mean()), "delta_bal_acc_desv": float(d.std()),
                     "frac_pliegues_positiva": float((d > 0).mean())})
    return pd.DataFrame(rows)


def ablation(dev, cols, clusters, cfg, seed, base_score):
    rows = []
    y = dev["label"].to_numpy()
    for cl in clusters:
        keep = [c for c in cols if c not in cl]
        if not keep:
            continue
        oof = cv_oof(dev, keep, cfg, seed)
        score = metrics(y, oof)["balanced_accuracy"]
        rows.append({"cluster_quitado": cluster_name(cl), "variables": cl,
                     "bal_acc_sin_cluster": score, "perdida": base_score - score})
    return pd.DataFrame(rows).sort_values("perdida", ascending=False)


def boruta(dev, cols, cfg, seed):
    X = matrix(dev, cols)
    med = np.nanmedian(X, axis=0)
    X = np.where(np.isnan(X), med, X)
    y = dev["label"].to_numpy()
    n_iter = int(cfg["importance"]["boruta_iterations"])
    rng = np.random.default_rng(seed)
    hits = np.zeros(len(cols))
    for it in range(n_iter):
        shadow = np.column_stack([rng.permutation(X[:, j]) for j in range(X.shape[1])])
        rf = RandomForestClassifier(n_estimators=int(cfg["importance"]["boruta_trees"]),
                                    max_depth=8, class_weight="balanced_subsample",
                                    n_jobs=-1, random_state=seed + it)
        rf.fit(np.hstack([X, shadow]), y)
        imp = rf.feature_importances_
        hits += imp[:len(cols)] > imp[len(cols):].max()
    p_hi = stats.binom.sf(hits - 1, n_iter, 0.5)
    p_lo = stats.binom.cdf(hits, n_iter, 0.5)
    alpha = 0.05 / len(cols)
    decision = np.where(p_hi < alpha, "CONFIRMADA", np.where(p_lo < alpha, "RECHAZADA", "TENTATIVA"))
    return pd.DataFrame({"variable": cols, "hits": hits.astype(int), "iteraciones": n_iter,
                         "decision": decision}).sort_values("hits", ascending=False)


def t_vs_y(cfg, dev, allowed):
    """Subanálisis dentro de enanas: ¿qué separa T de Y? Incluye Spitzer de UltracoolSheet
    (solo existe para enanas, por eso NO puede usarse contra estrellas)."""
    sub = dev.loc[dev["label"].isin(["T", "Y"])].copy()
    rows = []
    ucs_path = Path(cfg["paths"]["ultracoolsheet"])
    if ucs_path.is_file() and "name" in sub.columns:
        ucs = pd.read_csv(ucs_path, low_memory=False, usecols=["name", "ch1", "ch2"])
        ucs = ucs.drop_duplicates("name")
        ucs["spitzer_ch1_ch2"] = pd.to_numeric(ucs["ch1"], errors="coerce") - pd.to_numeric(ucs["ch2"], errors="coerce")
        sub = sub.merge(ucs[["name", "spitzer_ch1_ch2"]], on="name", how="left")
    y = (sub["label"] == "Y").astype(int).to_numpy()
    for c in [c for c in sub.columns if c in allowed or c == "spitzer_ch1_ch2"]:
        x = pd.to_numeric(sub[c], errors="coerce")
        m = x.notna().to_numpy()
        if ((y == 0) & m).sum() >= 10 and ((y == 1) & m).sum() >= 10 and x[m].nunique() > 2:
            auc = roc_auc_score(y[m], x[m])
            rows.append({"variable": c, "auc_Y": float(auc), "auc_simetrica": float(max(auc, 1 - auc)),
                         "n_T": int(((y == 0) & m).sum()), "n_Y": int(((y == 1) & m).sum())})
    return pd.DataFrame(rows).sort_values("auc_simetrica", ascending=False) if rows else pd.DataFrame()


def run(cfg: dict, out: Path, feat_dir: Path, split_dir: Path, log) -> dict:
    t = load_saved(feat_dir / "features")
    split = load_saved(split_dir / "particion")
    meta = json.loads((feat_dir / "feature_groups.json").read_text(encoding="utf-8"))
    groups, sets = meta["groups"], meta["feature_sets"]
    names = load_saved_objects_names(cfg)
    t = t.merge(split[["oid", "role", "cv_fold"]], on="oid")
    if names is not None:
        t = t.merge(names, on="oid", how="left")
    dev = t.loc[t["role"] == "dev"].reset_index(drop=True)
    seed = int(cfg["seed"])
    thr = float(cfg["robustness"]["corr_cluster_threshold"])
    result = {}
    warnings = []
    for set_name in ("E1_nucleo_fisico", "E2_nucleo_mas_gaia"):
        cols = usable(dev, expand(groups, sets[set_name]))
        if not cols:
            continue
        d = out / set_name
        d.mkdir(parents=True, exist_ok=True)
        clusters = correlation_clusters(dev, cols, thr)
        oof = cv_oof(dev, cols, cfg, seed)
        base = metrics(dev["label"].to_numpy(), oof)["balanced_accuracy"]
        perm = permutation_by_groups(dev, cols, clusters, cfg, seed)
        abl = ablation(dev, cols, clusters, cfg, seed, base)
        Xi = matrix(dev, cols)
        Xi = np.where(np.isnan(Xi), np.nanmedian(Xi, axis=0), Xi)
        mi = pd.DataFrame({"variable": cols, "info_mutua": mutual_info_classif(
            Xi, dev["label"], random_state=seed)}).sort_values("info_mutua", ascending=False)
        bor = boruta(dev, cols, cfg, seed)
        perm.to_csv(d / "permutacion.csv", index=False)
        abl.to_csv(d / "ablacion_por_cluster.csv", index=False)
        mi.to_csv(d / "informacion_mutua.csv", index=False)
        bor.to_csv(d / "boruta.csv", index=False)
        pc = perm.loc[perm["tipo"] == "cluster"].copy()
        pos = pc["delta_bal_acc_media"].clip(lower=0)
        share = float(pos.max() / pos.sum()) if pos.sum() > 0 else None
        top = pc.loc[pc["delta_bal_acc_media"].idxmax()] if len(pc) else None
        if share is not None and share > cfg["robustness"]["dominance_warning_share"]:
            warnings.append(f"{set_name}: el cluster '{top['unidad']}' concentra {share:.0%} de la importancia")
        consensus = consensus_table(perm, abl, mi, bor)
        consensus.to_csv(d / "consenso.csv", index=False)
        plot_importance(pc, d / "importancia_clusters.png", set_name)
        write_json(d / "clusters.json", {"umbral": thr, "clusters": clusters})
        result[set_name] = {"n_variables": len(cols), "bal_acc_oof": base, "n_clusters": len(clusters),
                            "cluster_dominante": None if top is None else top["unidad"],
                            "cuota_dominante": share,
                            "boruta_confirmadas": bor.loc[bor["decision"] == "CONFIRMADA", "variable"].tolist(),
                            "top_consenso": consensus.head(8)["variable"].tolist()}
        log.info("importancia %s: %s", set_name, result[set_name])
    allowed = {c for g, cols in groups.items() if not g.startswith("AUDIT") for c in cols}
    tvy = t_vs_y(cfg, dev, allowed)
    if len(tvy):
        tvy.to_csv(out / "subanalisis_T_vs_Y_auc.csv", index=False)
        result["T_vs_Y_top"] = tvy.head(6)[["variable", "auc_simetrica", "n_Y"]].to_dict(orient="records")
    write_json(out / "importancia_resumen.json", result)
    return {"summary": result, "warnings": warnings}


def load_saved_objects_names(cfg):
    from .data import load_objects
    obj, _ = load_objects(cfg)
    return obj[["oid", "name"]] if "name" in obj.columns else None


def consensus_table(perm, abl, mi, bor) -> pd.DataFrame:
    pv = perm.loc[perm["tipo"] == "variable"].assign(variable=lambda d: d["variables"].map(lambda v: v[0]))
    tab = pv[["variable", "delta_bal_acc_media"]].rename(columns={"delta_bal_acc_media": "perm_individual"})
    cl_rows = []
    for _, r in perm.loc[perm["tipo"] == "cluster"].iterrows():
        for v in r["variables"]:
            cl_rows.append({"variable": v, "perm_cluster": r["delta_bal_acc_media"], "cluster": r["unidad"]})
    tab = tab.merge(pd.DataFrame(cl_rows), on="variable", how="left")
    ab_rows = [{"variable": v, "perdida_ablacion_cluster": r["perdida"]}
               for _, r in abl.iterrows() for v in r["variables"]]
    tab = tab.merge(pd.DataFrame(ab_rows), on="variable", how="left")
    tab = tab.merge(mi, on="variable", how="left").merge(bor[["variable", "hits", "decision"]], on="variable", how="left")
    for c in ("perm_individual", "perm_cluster", "perdida_ablacion_cluster", "info_mutua", "hits"):
        tab[f"rango_{c}"] = tab[c].rank(ascending=False)
    tab["rango_medio"] = tab[[c for c in tab.columns if c.startswith("rango_")]].mean(axis=1)
    return tab.sort_values("rango_medio")


def plot_importance(pc: pd.DataFrame, path: Path, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pc = pc.sort_values("delta_bal_acc_media")
    fig, ax = plt.subplots(figsize=(7, 0.35 * len(pc) + 1.2))
    ax.barh(pc["unidad"], pc["delta_bal_acc_media"], xerr=pc["delta_bal_acc_desv"], color="#4c72b0")
    ax.set_xlabel("caída de balanced accuracy al permutar el cluster")
    ax.set_title(title, fontsize=9)
    ax.tick_params(axis="y", labelsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
