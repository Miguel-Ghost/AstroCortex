"""Etapa 3: EDA.

A) Descriptivo de TODAS las columnas de TODAS las tablas de entrada (sin etiquetas).
B) EDA por clase de las variables derivadas, SOLO con el conjunto de desarrollo:
   normalidad, Kruskal–Wallis + ε², Mann–Whitney por pares + delta de Cliff,
   χ² de faltantes + V de Cramér, KS entre pliegues espaciales, correlaciones.
   Corrección de Benjamini–Hochberg por familia de pruebas.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from .common import write_json
from .data import find_table, load_catalog, load_objects, read_table
from .s1_features import load_saved

CLASSES = ["star", "M", "L", "T", "Y"]
PAIRS = [("star", "T"), ("star", "Y"), ("T", "Y"), ("L", "T"), ("M", "T"), ("star", "L")]


def describe_table(df: pd.DataFrame, name: str) -> dict:
    cols = []
    for c in df.columns:
        s = df[c]
        item = {"columna": c, "dtype": str(s.dtype), "n": int(len(s)),
                "nulos": int(s.isna().sum()), "frac_nulos": float(s.isna().mean()) if len(s) else None}
        try:
            item["distintos"] = int(s.nunique(dropna=True))
        except TypeError:
            item["distintos"] = None
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            x = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
            if len(x):
                q = x.quantile([0, .01, .05, .25, .5, .75, .95, .99, 1]).to_list()
                item.update({"min": q[0], "p01": q[1], "p05": q[2], "p25": q[3], "mediana": q[4],
                             "p75": q[5], "p95": q[6], "p99": q[7], "max": q[8],
                             "media": float(x.mean()), "desv": float(x.std()) if len(x) > 1 else None,
                             "asimetria": float(stats.skew(x)) if len(x) > 2 else None,
                             "curtosis": float(stats.kurtosis(x)) if len(x) > 3 else None})
        else:
            vc = s.astype("string").value_counts(dropna=True).head(10)
            item["top"] = {str(k): int(v) for k, v in vc.items()}
        cols.append(item)
    return {"tabla": name, "filas": int(len(df)), "columnas": len(df.columns), "detalle": cols}


def bh(pvals: list[float]) -> list[float]:
    p = np.asarray(pvals, float)
    n = len(p)
    if n == 0:
        return []
    order = np.argsort(p)
    q = np.empty(n)
    run_min = 1.0
    for rank in range(n - 1, -1, -1):
        i = order[rank]
        run_min = min(run_min, p[i] * n / (rank + 1))
        q[i] = run_min
    return q.tolist()


def cliffs_delta(a, b) -> float:
    a, b = np.asarray(a), np.asarray(b)
    if len(a) * len(b) > 4_000_000:
        rng = np.random.default_rng(1)
        a = rng.choice(a, min(len(a), 2000), replace=False)
        b = rng.choice(b, min(len(b), 2000), replace=False)
    u = stats.mannwhitneyu(a, b, alternative="two-sided").statistic
    return float(2 * u / (len(a) * len(b)) - 1)


def raw_eda(cfg: dict, out: Path, log) -> list[str]:
    raw_dir = out / "A_descriptivo_tablas"
    raw_dir.mkdir(parents=True, exist_ok=True)
    done = []
    proc = Path(cfg["paths"]["processed"])
    for f in sorted(list(proc.glob("*.parquet")) + list(proc.glob("*.csv"))):
        write_json(raw_dir / f"{f.stem}.json", describe_table(read_table(f), f.name))
        done.append(f.name)
    ucs = Path(cfg["paths"]["ultracoolsheet"])
    if ucs.is_file():
        write_json(raw_dir / "UltracoolSheet_Main.json",
                   describe_table(pd.read_csv(ucs, low_memory=False), ucs.name))
        done.append(ucs.name)
    _, osha = load_objects(cfg)
    for name in cfg["catalogs"]:
        frame, _ = load_catalog(cfg, name, osha)
        write_json(raw_dir / f"noirlab_{name}.json", describe_table(frame, f"noirlab_{name}"))
        done.append(f"noirlab_{name}")
    idx = Path(cfg["paths"]["spherex_index"])
    if idx.is_file():
        with idx.open(encoding="utf-8") as fh:
            rows = [json.loads(l) for l in fh if l.strip()]
        write_json(raw_dir / "spherex_pilot_index.json", describe_table(pd.DataFrame(rows), idx.name))
        done.append(idx.name)
    log.info("EDA descriptivo: %d tablas", len(done))
    return done


def class_eda(cfg: dict, out: Path, feat_dir: Path, split_dir: Path, log) -> dict:
    t = load_saved(feat_dir / "features")
    split = load_saved(split_dir / "particion")
    groups = json.loads((feat_dir / "feature_groups.json").read_text(encoding="utf-8"))["groups"]
    t = t.merge(split[["oid", "role", "cv_fold"]], on="oid")
    dev = t.loc[t["role"] == "dev"].copy()
    feats = [c for g, cols in groups.items() for c in cols]
    feats = list(dict.fromkeys(feats))
    tests, per_class = [], []
    for c in feats:
        x = pd.to_numeric(dev[c], errors="coerce").replace([np.inf, -np.inf], np.nan)
        by = {k: x[dev["label"] == k].dropna().to_numpy() for k in CLASSES}
        for k, v in by.items():
            row = {"variable": c, "clase": k, "n": int(len(v)),
                   "cobertura": float((dev["label"] == k).pipe(lambda m: x[m].notna().mean()))}
            if len(v):
                row.update({"p05": float(np.quantile(v, .05)), "mediana": float(np.median(v)),
                            "p95": float(np.quantile(v, .95)), "media": float(v.mean()),
                            "desv": float(v.std(ddof=1)) if len(v) > 1 else None})
            if len(v) >= 20 and np.unique(v).size > 3:
                s = v if len(v) <= 5000 else np.random.default_rng(2).choice(v, 5000, replace=False)
                row["normaltest_p"] = float(stats.normaltest(s).pvalue)
                tests.append({"familia": "normalidad", "variable": c, "clase": k, "p": row["normaltest_p"]})
            per_class.append(row)
        valid = [v for v in by.values() if len(v) >= 5]
        if len(valid) >= 2 and np.unique(np.concatenate(valid)).size > 1:
            h = stats.kruskal(*valid)
            n = sum(len(v) for v in valid)
            eps2 = float((h.statistic - len(valid) + 1) / (n - len(valid))) if n > len(valid) else None
            tests.append({"familia": "kruskal", "variable": c, "p": float(h.pvalue),
                          "H": float(h.statistic), "epsilon2": eps2})
        for a, b in PAIRS:
            if len(by[a]) >= 5 and len(by[b]) >= 5:
                p = stats.mannwhitneyu(by[a], by[b], alternative="two-sided").pvalue
                tests.append({"familia": "mannwhitney", "variable": c, "par": f"{a}_vs_{b}",
                              "p": float(p), "cliffs_delta": cliffs_delta(by[b], by[a])})
        miss = pd.crosstab(dev["label"], x.isna())
        if miss.shape == (len(miss.index), 2) and miss.shape[0] >= 2:
            chi2, p, dof, exp = stats.chi2_contingency(miss)
            v = float(np.sqrt(chi2 / (miss.values.sum() * (min(miss.shape) - 1))))
            tests.append({"familia": "faltantes_chi2", "variable": c, "p": float(p),
                          "cramers_v": v, "min_esperado": float(exp.min()),
                          "frac_faltante_por_clase": x.isna().groupby(dev["label"]).mean().round(3).to_dict()})
        for k in ("star", "T"):
            sub = dev.loc[dev["label"] == k]
            xs = pd.to_numeric(sub[c], errors="coerce")
            worst = None
            for fold in sorted(sub["cv_fold"].unique()):
                a = xs[sub["cv_fold"] == fold].dropna()
                b = xs[sub["cv_fold"] != fold].dropna()
                if len(a) >= 20 and len(b) >= 20:
                    r = stats.ks_2samp(a, b)
                    if worst is None or r.statistic > worst["D"]:
                        worst = {"D": float(r.statistic), "p": float(r.pvalue), "fold": int(fold)}
            if worst:
                tests.append({"familia": "ks_entre_zonas", "variable": c, "clase": k, **worst})
    fams = {}
    for i, r in enumerate(tests):
        fams.setdefault(r["familia"], []).append(i)
    for fam, idxs in fams.items():
        for i, q in zip(idxs, bh([tests[i]["p"] for i in idxs])):
            tests[i]["q_bh"] = q
    pd.DataFrame(per_class).to_csv(out / "B_estadisticos_por_clase.csv", index=False)
    pd.DataFrame(tests).to_csv(out / "B_pruebas.csv", index=False)

    core = [c for g in ("color_wise", "color_2mass", "color_nir_mir", "movimiento", "gaia")
            for c in groups.get(g, [])]
    corr = dev[core].apply(pd.to_numeric, errors="coerce").corr(method="spearman", min_periods=30)
    corr.round(3).to_csv(out / "B_correlacion_spearman.csv")
    figures(dev, core, corr, out)

    kr = pd.DataFrame([r for r in tests if r["familia"] == "kruskal"]).sort_values(
        "epsilon2", ascending=False)
    ks = pd.DataFrame([r for r in tests if r["familia"] == "ks_entre_zonas"])
    mis = pd.DataFrame([r for r in tests if r["familia"] == "faltantes_chi2"])
    summary = {
        "n_dev": int(len(dev)), "n_tests": len(tests),
        "top_kruskal_epsilon2": kr.head(10)[["variable", "epsilon2", "q_bh"]].to_dict(orient="records"),
        "faltantes_mas_asociados": mis.sort_values("cramers_v", ascending=False).head(8)[
            ["variable", "cramers_v"]].to_dict(orient="records") if len(mis) else [],
        "zonas_heterogeneas_D>0.2": ks.loc[ks["D"] > 0.2, ["variable", "clase", "D"]].to_dict(
            orient="records") if len(ks) else [],
    }
    write_json(out / "B_resumen.json", summary)
    return summary


def figures(dev: pd.DataFrame, cols: list[str], corr: pd.DataFrame, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig_dir = out / "figuras"
    fig_dir.mkdir(exist_ok=True)
    colors = {"star": "#7f7f7f", "M": "#d62728", "L": "#ff7f0e", "T": "#1f77b4", "Y": "#9467bd"}
    for c in cols:
        x = pd.to_numeric(dev[c], errors="coerce")
        if x.notna().sum() < 20:
            continue
        lo, hi = np.nanquantile(x, [0.005, 0.995])
        if not np.isfinite(lo) or lo == hi:
            continue
        bins = np.linspace(lo, hi, 50)
        fig, ax = plt.subplots(figsize=(6, 3.6))
        for k in CLASSES:
            v = x[dev["label"] == k].dropna()
            if len(v) >= 5:
                ax.hist(v.clip(lo, hi), bins=bins, density=True, histtype="step", lw=1.6,
                        color=colors[k], label=f"{k} (n={len(v)})")
        ax.set_xlabel(c)
        ax.set_ylabel("densidad")
        ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(fig_dir / f"hist_{c}.png", dpi=110)
        plt.close(fig)
    if len(corr):
        fig, ax = plt.subplots(figsize=(0.45 * len(corr) + 2, 0.45 * len(corr) + 1.5))
        im = ax.imshow(corr.to_numpy(), vmin=-1, vmax=1, cmap="RdBu_r")
        ax.set_xticks(range(len(corr)), corr.columns, rotation=90, fontsize=7)
        ax.set_yticks(range(len(corr)), corr.index, fontsize=7)
        fig.colorbar(im, ax=ax, shrink=0.7, label="Spearman ρ")
        fig.tight_layout()
        fig.savefig(fig_dir / "correlacion_spearman.png", dpi=110)
        plt.close(fig)


def run(cfg: dict, out: Path, feat_dir: Path, split_dir: Path, log) -> dict:
    tables = raw_eda(cfg, out, log)
    summary = class_eda(cfg, out, feat_dir, split_dir, log)
    return {"summary": {"tablas_descritas": len(tables), "n_pruebas": summary["n_tests"],
                        "top_kruskal": [r["variable"] for r in summary["top_kruskal_epsilon2"][:5]]}}
