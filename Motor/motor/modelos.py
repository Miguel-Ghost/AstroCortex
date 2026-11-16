"""Modelos comparados (Random Forest, XGBoost, red neuronal MLP) con la misma entrada y los mismos pliegues.

Entrada común: matriz con NaN → imputación por la mediana del entrenamiento del pliegue (la misma que
aplicará el backend con `fill_values`). La red además recorta a percentiles y estandariza DENTRO de su
grafo, así el ONNX exportado no depende de pasos externos.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (average_precision_score, balanced_accuracy_score, confusion_matrix, f1_score,
                             precision_recall_fscore_support)


# ----------------------------------------------------------------------------- utilidades
def pesos_clase(y: np.ndarray, n_clases: int, potencia: float) -> np.ndarray:
    """Peso por clase (N / (K·n_c))^p, índice = código de clase. p=1 'balanced', p=0 sin peso."""
    counts = np.bincount(y, minlength=n_clases).astype(float)
    w = np.where(counts > 0, (len(y) / (n_clases * np.maximum(counts, 1))) ** potencia, 0.0)
    return w


def medianas(X: np.ndarray) -> np.ndarray:
    with np.errstate(all="ignore"):
        m = np.nanmedian(X, axis=0)
    return np.where(np.isfinite(m), m, 0.0)


def imputar(X: np.ndarray, med: np.ndarray) -> np.ndarray:
    Xi = X.copy()
    r, c = np.where(~np.isfinite(Xi))
    Xi[r, c] = med[c]
    return Xi


# ----------------------------------------------------------------------------- RF / XGB
def ajustar_rf(X, y, w, cfg_m: dict, seed: int):
    from sklearn.ensemble import RandomForestClassifier
    p = cfg_m["rf"]
    m = RandomForestClassifier(n_estimators=int(p["n_estimators"]), min_samples_leaf=int(p["min_samples_leaf"]),
                               max_features=p["max_features"], n_jobs=-1, random_state=seed)
    return m.fit(X, y, sample_weight=w)


def ajustar_xgb(X, y, w, cfg_m: dict, seed: int, n_clases: int):
    from xgboost import XGBClassifier
    p = cfg_m["xgb"]
    m = XGBClassifier(n_estimators=int(p["n_estimators"]), max_depth=int(p["max_depth"]),
                      learning_rate=float(p["learning_rate"]), subsample=float(p["subsample"]),
                      colsample_bytree=float(p["colsample_bytree"]), min_child_weight=float(p["min_child_weight"]),
                      reg_lambda=float(p["reg_lambda"]), tree_method="hist", n_jobs=-1, random_state=seed,
                      objective="binary:logistic" if n_clases == 2 else "multi:softprob",
                      eval_metric="logloss" if n_clases == 2 else "mlogloss")
    return m.fit(X, y, sample_weight=w)


def proba_sklearn(model, X: np.ndarray, n_clases: int) -> np.ndarray:
    p = model.predict_proba(X)
    out = np.zeros((len(X), n_clases))
    for j, c in enumerate(model.classes_):
        out[:, int(c)] = p[:, j]
    return out


# ----------------------------------------------------------------------------- MLP (PyTorch)
def _torch():
    import torch
    return torch


def construir_red(n_in: int, n_out: int, capas: list[int], dropout: float, lo, hi, mean, std):
    torch = _torch()
    nn = torch.nn

    class Red(nn.Module):
        def __init__(self):
            super().__init__()
            self.register_buffer("lo", torch.as_tensor(lo, dtype=torch.float32))
            self.register_buffer("hi", torch.as_tensor(hi, dtype=torch.float32))
            self.register_buffer("mean", torch.as_tensor(mean, dtype=torch.float32))
            self.register_buffer("std", torch.as_tensor(std, dtype=torch.float32))
            layers, prev = [], n_in
            for h in capas:
                layers += [nn.Linear(prev, h), nn.ReLU(), nn.Dropout(dropout)]
                prev = h
            layers.append(nn.Linear(prev, n_out))
            self.net = nn.Sequential(*layers)

        def forward(self, x):
            x = torch.maximum(torch.minimum(x, self.hi), self.lo)
            return self.net((x - self.mean) / self.std)

    return Red()


def ajustar_mlp(X, y, w_clase: np.ndarray, X_val, y_val, cfg_m: dict, seed: int, n_clases: int):
    """X ya imputada. Parada temprana con la pérdida ponderada en (X_val, y_val)."""
    torch = _torch()
    p = cfg_m["mlp"]
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    lo_p, hi_p = p["recorte_percentil"]
    lo, hi = np.percentile(X, lo_p, axis=0), np.percentile(X, hi_p, axis=0)
    Xc = np.clip(X, lo, hi)
    mean, std = Xc.mean(axis=0), Xc.std(axis=0)
    std = np.where(std > 1e-9, std, 1.0)
    net = construir_red(X.shape[1], n_clases, p["capas"], float(p["dropout"]), lo, hi, mean, std).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=float(p["lr"]), weight_decay=float(p["weight_decay"]))
    wt = torch.as_tensor(w_clase, dtype=torch.float32, device=dev)
    loss_fn = torch.nn.CrossEntropyLoss(weight=wt)
    Xt = torch.as_tensor(X, dtype=torch.float32, device=dev)
    yt = torch.as_tensor(y, dtype=torch.long, device=dev)
    Xv = torch.as_tensor(X_val, dtype=torch.float32, device=dev)
    yv = torch.as_tensor(y_val, dtype=torch.long, device=dev)
    best, best_state, wait = np.inf, None, 0
    bs = int(p["batch"])
    for epoch in range(int(p["epocas_max"])):
        net.train()
        order = rng.permutation(len(X))
        for i in range(0, len(order), bs):
            b = torch.as_tensor(order[i:i + bs], device=dev)
            opt.zero_grad()
            loss = loss_fn(net(Xt[b]), yt[b])
            loss.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            vl = float(loss_fn(net(Xv), yv)) if len(X_val) else 0.0
        if vl < best - 1e-4:
            best, wait = vl, 0
            best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
        else:
            wait += 1
            if wait >= int(p["paciencia"]):
                break
    if best_state is not None:
        net.load_state_dict(best_state)
    net.eval()
    net.epocas_usadas = epoch + 1
    return net.cpu()


def proba_mlp(net, X: np.ndarray) -> np.ndarray:
    torch = _torch()
    with torch.no_grad():
        return torch.softmax(net(torch.as_tensor(X, dtype=torch.float32)), dim=1).numpy()


# ----------------------------------------------------------------------------- métricas
def metricas(y: np.ndarray, proba: np.ndarray, clases: list[str], positivas: list[str]) -> dict:
    """y: códigos enteros. positivas: clases de interés (T,Y o cold_brown_dwarf) para AP y precisión/recall."""
    pred = np.argmax(proba, axis=1)
    present = sorted(set(y.tolist()))
    prec, rec, f1, sup = precision_recall_fscore_support(y, pred, labels=present, zero_division=0)
    pos_idx = [clases.index(c) for c in positivas if c in clases]
    is_pos = np.isin(y, pos_idx).astype(int)
    p_pos = proba[:, pos_idx].sum(axis=1)
    pred_pos = np.isin(pred, pos_idx)
    out = {
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, labels=present, average="macro", zero_division=0)),
        "ap_positivas": float(average_precision_score(is_pos, p_pos)) if is_pos.any() else None,
        "precision_positivas": float(is_pos[pred_pos].mean()) if pred_pos.any() else None,
        "recall_positivas": float(pred_pos[is_pos == 1].mean()) if is_pos.any() else None,
        "por_clase": {clases[c]: {"precision": float(a), "recall": float(b), "f1": float(f), "n": int(s)}
                      for c, a, b, f, s in zip(present, prec, rec, f1, sup)},
        "confusion_etiquetas": [clases[c] for c in present],
        "confusion": confusion_matrix(y, pred, labels=present).tolist(),
    }
    return out


def resumen_corto(m: dict, clases: list[str]) -> dict:
    out = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()
           if k in ("balanced_accuracy", "macro_f1", "ap_positivas", "precision_positivas", "recall_positivas")}
    for c in clases:
        if c in m["por_clase"]:
            out[f"recall_{c}"] = round(m["por_clase"][c]["recall"], 4)
    return out


def ic_recall(y: np.ndarray, pred: np.ndarray, idx: list[int], n: int = 2000, seed: int = 0):
    sel = np.flatnonzero(np.isin(y, idx))
    if len(sel) < 3:
        return None
    hits = np.isin(pred[sel], idx).astype(float)
    sims = np.random.default_rng(seed).choice(hits, (n, len(hits)), replace=True).mean(axis=1)
    return [float(np.quantile(sims, 0.025)), float(np.quantile(sims, 0.975))]
