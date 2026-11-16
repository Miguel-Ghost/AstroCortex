"""Modelo, validación cruzada espacial, métricas, aumento por apagado de grupos."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (average_precision_score, balanced_accuracy_score,
                             confusion_matrix, f1_score, precision_recall_fscore_support)

CLASSES = ["star", "M", "L", "T", "Y"]


def class_weights(y: np.ndarray, power: float) -> dict:
    """Peso por clase = (N / (K·n_c))^power. power=1 es 'balanced' (extremo con 50 Y:
    el modelo sobre-predice Y); power=0.5 lo atenúa; power=0 no pondera."""
    labels, counts = np.unique(y, return_counts=True)
    w = (len(y) / (len(labels) * counts)) ** power
    return dict(zip(labels, w))


def make_model(cfg: dict, seed: int) -> HistGradientBoostingClassifier:
    m = cfg["model"]
    return HistGradientBoostingClassifier(
        max_iter=m["max_iter"], learning_rate=m["learning_rate"], max_leaf_nodes=m["max_leaf_nodes"],
        min_samples_leaf=m["min_samples_leaf"], l2_regularization=m["l2_regularization"],
        early_stopping=False, random_state=seed)


def fit_model(cfg: dict, seed: int, X: np.ndarray, y: np.ndarray) -> HistGradientBoostingClassifier:
    power = float(cfg["model"].get("class_weight_power", 1.0))
    cw = class_weights(y, power)
    return make_model(cfg, seed).fit(X, y, sample_weight=np.array([cw[v] for v in y]))


def matrix(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    return df[cols].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).to_numpy(float)


def correlation_clusters(df: pd.DataFrame, cols: list[str], thr: float) -> list[list[str]]:
    """Agrupa variables con |Spearman| >= thr (componentes conexas)."""
    corr = df[cols].apply(pd.to_numeric, errors="coerce").corr(method="spearman", min_periods=30).abs()
    # Enlace PROMEDIO (no simple): evita el "encadenamiento" en que A~B, B~C, C~D
    # terminan en un solo grupo aunque A y D no se parezcan. Con datos reales el
    # enlace simple juntó 10 de 15 variables en un cluster y vaciaba la prueba de estrés.
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    if len(cols) == 1:
        return [list(cols)]
    dist = (1 - corr.fillna(0).to_numpy())
    np.fill_diagonal(dist, 0)
    dist = np.clip((dist + dist.T) / 2, 0, 1)
    labels = fcluster(linkage(squareform(dist, checks=False), method="average"),
                      t=1 - thr, criterion="distance")
    groups = {}
    for c, k in zip(cols, labels):
        groups.setdefault(int(k), []).append(c)
    return sorted(groups.values(), key=lambda g: (-len(g), g[0]))


def cluster_name(cluster: list[str]) -> str:
    return "+".join(cluster) if len(cluster) <= 3 else f"{cluster[0]}+{len(cluster) - 1}más"


def dropout_augment(X: np.ndarray, y: np.ndarray, clusters_idx: list[list[int]], p: float,
                    copies: int, rng: np.random.Generator, forced: list[int] | None = None):
    """Copias del entrenamiento donde cada grupo correlacionado se apaga (NaN) con prob. p.
    El grupo dominante (forced) se apaga siempre en la mitad de las copias, para que el
    modelo aprenda rutas alternativas y no dependa de una sola variable."""
    Xs, ys = [X], [y]
    for k in range(copies):
        Xc = X.copy()
        for g in clusters_idx:
            m = rng.random(len(X)) < p
            Xc[np.ix_(m, g)] = np.nan
        if forced is not None and k % 2 == 0:
            m = rng.random(len(X)) < 0.5
            Xc[np.ix_(m, forced)] = np.nan
        Xs.append(Xc)
        ys.append(y)
    return np.vstack(Xs), np.concatenate(ys)


def proba_full(model, X: np.ndarray) -> np.ndarray:
    p = model.predict_proba(X)
    out = np.zeros((len(X), len(CLASSES)))
    for j, c in enumerate(model.classes_):
        out[:, CLASSES.index(c)] = p[:, j]
    return out


def cv_oof(dev: pd.DataFrame, cols: list[str], cfg: dict, seed: int, augment=None,
           mask_cols: list[str] | None = None, return_models=False):
    """Predicciones fuera de pliegue. augment(Xtr, ytr, rng) -> (X, y) opcional."""
    X = matrix(dev, cols)
    y = dev["label"].to_numpy()
    folds = dev["cv_fold"].to_numpy()
    oof = np.full((len(dev), len(CLASSES)), np.nan)
    models = []
    rng = np.random.default_rng(seed)
    for k in sorted(np.unique(folds)):
        tr, va = folds != k, folds == k
        Xtr, ytr = X[tr], y[tr]
        if augment is not None:
            Xtr, ytr = augment(Xtr, ytr, rng)
        model = fit_model(cfg, seed + int(k), Xtr, ytr)
        Xva = X[va].copy()
        if mask_cols:
            Xva[:, [cols.index(c) for c in mask_cols]] = np.nan
        oof[va] = proba_full(model, Xva)
        models.append((k, model))
    return (oof, models) if return_models else oof


def metrics(y: np.ndarray, proba: np.ndarray, weights: np.ndarray | None = None) -> dict:
    pred = np.array(CLASSES)[np.argmax(proba, axis=1)]
    present = [c for c in CLASSES if c in set(y)]
    prec, rec, f1, sup = precision_recall_fscore_support(y, pred, labels=present, zero_division=0,
                                                         sample_weight=weights)
    is_ty = np.isin(y, ["T", "Y"]).astype(int)
    p_ty = proba[:, CLASSES.index("T")] + proba[:, CLASSES.index("Y")]
    out = {
        "balanced_accuracy": float(balanced_accuracy_score(y, pred, sample_weight=weights)),
        "macro_f1": float(f1_score(y, pred, labels=present, average="macro", zero_division=0,
                                   sample_weight=weights)),
        "ap_TY_vs_resto": float(average_precision_score(is_ty, p_ty, sample_weight=weights))
        if is_ty.any() else None,
        "por_clase": {c: {"precision": float(p), "recall": float(r), "f1": float(f), "n": int(s)}
                      for c, p, r, f, s in zip(present, prec, rec, f1, sup)},
        "confusion_labels": present,
        "confusion": confusion_matrix(y, pred, labels=present).tolist(),
    }
    ty_pred = np.isin(pred, ["T", "Y"])
    out["TY_binario"] = {
        "precision": float((is_ty[ty_pred] == 1).mean()) if ty_pred.any() else None,
        "recall": float(ty_pred[is_ty == 1].mean()) if is_ty.any() else None}
    return out


def bootstrap_recall(y, pred, cls: str, n: int = 2000, seed: int = 0) -> list[float] | None:
    idx = np.flatnonzero(y == cls)
    if len(idx) < 3:
        return None
    rng = np.random.default_rng(seed)
    hits = (pred[idx] == cls).astype(float)
    sims = rng.choice(hits, (n, len(hits)), replace=True).mean(axis=1)
    return [float(np.quantile(sims, 0.025)), float(np.quantile(sims, 0.975))]


def brightness_weights(df: pd.DataFrame, col: str = "cw_w2mpro") -> np.ndarray:
    """Repesa estrellas, M y L para que su distribución de W2 iguale a la de T+Y.
    Si el modelo empeora mucho con estos pesos, está usando el brillo como atajo."""
    w2 = pd.to_numeric(df[col], errors="coerce")
    ref = w2[df["label"].isin(["T", "Y"])].dropna()
    w = np.ones(len(df))
    if len(ref) < 20:
        return w
    bins = np.unique(np.nanquantile(ref, np.linspace(0, 1, 11)))
    ref_h = np.histogram(ref, bins)[0] / len(ref)
    for cls in ("star", "M", "L"):
        m = (df["label"] == cls).to_numpy()
        x = w2[m]
        h = np.histogram(x.dropna(), bins)[0]
        h = h / max(h.sum(), 1)
        b = np.clip(np.digitize(x, bins) - 1, 0, len(ref_h) - 1)
        ww = np.where(x.notna() & (x >= bins[0]) & (x <= bins[-1]),
                      ref_h[b] / np.where(h[b] > 0, h[b], np.inf), 0.0)
        if ww.sum() > 0:
            ww = ww * m.sum() / ww.sum()
        w[m] = ww
    return w
