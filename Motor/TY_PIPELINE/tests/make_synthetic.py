"""Genera datos SINTÉTICOS con el mismo esquema que los reales, para probar el pipeline
de punta a punta sin tocar los datos verdaderos. Todo queda marcado como sintético."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

N = {"star": 2400, "M": 300, "L": 500, "T": 320, "Y": 45}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(root: Path, seed: int = 7) -> None:
    rng = np.random.default_rng(seed)
    proc = root / "data" / "processed"
    proc.mkdir(parents=True, exist_ok=True)
    rows = []
    oid = 0
    fields = [(rng.uniform(0, 360), np.degrees(np.arcsin(rng.uniform(-1, 1)))) for _ in range(20)]
    for lab, n in N.items():
        for i in range(n):
            if lab == "star":
                f = i % len(fields)
                ra = (fields[f][0] + rng.normal(0, 0.3)) % 360
                dec = np.clip(fields[f][1] + rng.normal(0, 0.3), -89.9, 89.9)
            else:
                ra, dec = rng.uniform(0, 360), np.degrees(np.arcsin(rng.uniform(-1, 1)))
            rows.append({"oid": oid, "name": f"SYN {lab} {i}", "source": "gaia_field" if lab == "star" else "ultracoolsheet",
                         "label": lab, "ra": ra, "dec": dec, "epoch": 2016.0 if lab == "star" else rng.uniform(2000, 2020),
                         "pmra": 0.0, "pmdec": 0.0, "plx": np.nan,
                         "ucs_W1": np.nan, "ucs_W2": np.nan,
                         "gaia_source_id": 10**15 + oid if (lab == "star" or rng.random() < {"M": .9, "L": .6, "T": .1, "Y": 0}[lab]) else np.nan,
                         "gaia_field": (i % 20) if lab == "star" else np.nan})
            oid += 1
    obj = pd.DataFrame(rows)
    obj_path = proc / "objects.csv"
    obj.to_csv(obj_path, index=False)
    osha = sha(obj_path)

    lab = obj["label"].to_numpy()
    w1w2 = {"star": (0.05, 0.05), "M": (0.2, 0.08), "L": (0.45, 0.15), "T": (1.6, 0.5), "Y": (3.0, 0.6)}
    jw2 = {"star": (1.2, 0.4), "M": (2.2, 0.4), "L": (3.2, 0.5), "T": (4.0, 0.9), "Y": (7.0, 1.0)}
    mu = {"star": (0.01, 0.01), "M": (0.3, 0.2), "L": (0.4, 0.3), "T": (0.6, 0.4), "Y": (1.0, 0.6)}
    w2 = np.where(lab == "star", rng.uniform(9, 16, len(obj)), rng.uniform(11, 16.5, len(obj)))
    c = np.array([rng.normal(*w1w2[l]) for l in lab])
    w1 = w2 + c
    J = w2 + np.array([rng.normal(*jw2[l]) for l in lab])
    m = np.abs(np.array([rng.normal(*mu[l]) for l in lab]))
    ang = rng.uniform(0, 2 * np.pi, len(obj))
    jmiss = (J > 17) | ((lab == "Y") & (rng.random(len(obj)) < .8))

    cat_root = root / "CLASIFICADOR_TY" / "data" / "catalogos_noirlab"
    def write_cat(name, frame):
        d = cat_root / name
        d.mkdir(parents=True, exist_ok=True)
        for k in range(0, len(obj), 500):
            part = frame.loc[frame["oid"].between(k, k + 499)]
            p = d / f"chunk_{k // 1000:04d}_batch_{(k % 1000) // 500:04d}.csv"
            part.to_csv(p, index=False)
            (p.with_suffix(".json")).write_text(json.dumps({"input_sha256": osha, "response_sha256": sha(p),
                                                            "complete": True, "synthetic": True}), encoding="utf-8")

    jit = lambda s: rng.normal(0, s / 3600, len(obj))  # noqa: E731
    base = pd.DataFrame({"oid": obj["oid"], "ra_q": obj["ra"], "dec_q": obj["dec"]})
    cw = base.assign(source_id=[f"cw{i}" for i in obj.oid], ra=obj.ra + jit(0.3), dec=obj.dec + jit(0.3),
                     w1mpro=w1, w1sigmpro=0.02 + 0.02 * (w1 - 9), w2mpro=w2, w2sigmpro=0.02 + 0.01 * (w2 - 9),
                     pmra=m * np.cos(ang), pmdec=m * np.sin(ang), cc_flags="0000", ab_flags="00",
                     w1snr=50 / (1 + np.exp(w1 - 15)), w2snr=60 / (1 + np.exp(w2 - 15)))
    dup = cw.sample(60, random_state=1).assign(ra=lambda d: d.ra + 1.5 / 3600, w2mpro=lambda d: d.w2mpro + 1)
    write_cat("catwise", pd.concat([cw, dup]).sort_values("oid"))
    aw = base.assign(designation="J", ra=obj.ra + jit(0.4), dec=obj.dec + jit(0.4), w1mpro=w1 + rng.normal(0, .03, len(obj)),
                     w1sigmpro=0.03, w2mpro=w2 + rng.normal(0, .03, len(obj)), w2sigmpro=0.03, cc_flags="0000",
                     ph_qual=np.where(lab == "Y", "UAUU", "AAUU"), var_flg="11nn", nb=1, na=0, ext_flg=0)
    write_cat("allwise", aw.loc[rng.random(len(aw)) < .9])
    tm = base.assign(designation="X", ra=obj.ra + jit(0.3), dec=obj.dec + jit(0.3), j_m=J, j_msigcom=0.03,
                     h_m=J - np.where(lab == "star", .4, .7), h_msigcom=0.03, k_m=J - np.where(lab == "star", .5, 1.0),
                     k_msigcom=0.04, ph_qual="AAA", cc_flg="000", rd_flg="222", bl_flg="111")
    write_cat("tmass", tm.loc[~jmiss])
    f1, f2 = 10 ** (-0.4 * (w1 - 22.5)), 10 ** (-0.4 * (w2 - 22.5))
    uw = base.assign(unwise_objid="u", ra=obj.ra + jit(0.5), dec=obj.dec + jit(0.5), flux_w1=f1, dflux_w1=f1 * .03,
                     flux_w2=f2, dflux_w2=f2 * .03, qf_w1=1, qf_w2=1, fracflux_w1=.9, fracflux_w2=.9,
                     flags_unwise_w1=0, flags_unwise_w2=0, primary=1)
    write_cat("unwise", uw)

    g = obj.loc[obj.gaia_source_id.notna(), ["oid"]].copy()
    gl = obj.set_index("oid").loc[g.oid, "label"].to_numpy()
    G = w2[g.oid] + np.where(gl == "star", 2.0, 5.0) + rng.normal(0, .3, len(g))
    g = g.assign(source_id=obj.gaia_source_id[g.oid].astype("int64").to_numpy(), parallax=np.where(gl == "star", 0.5, 30.0),
                 parallax_error=0.2, pmra=m[g.oid] * 1000, pmdec=0.0, ruwe=1.0, phot_g_mean_mag=G,
                 phot_bp_mean_mag=G + np.where(gl == "star", .5, 1.5), phot_rp_mean_mag=G - np.where(gl == "star", .5, 1.5),
                 phot_bp_rp_excess_factor=1.2, n_match=1)
    g.to_csv(proc / "xm_gaia.csv", index=False)
    targets = obj.loc[obj.label.isin(["star", "T", "Y"])].groupby("label").head(1)
    st = targets[["oid", "name", "label", "ra", "dec"]].copy()
    st.to_csv(proc / "spherex_sample_targets.csv", index=False)
    ph = []
    for _, r in st.iterrows():
        for wl in np.linspace(0.75, 5.0, 120):
            f = 1.0 if r.label == "star" else (0.2 + (0.8 if 3.9 < wl < 4.3 else 0.0) - (0.15 if 3.2 < wl < 3.4 else 0))
            ph.append({"oid": r.oid, "wl": wl, "flux_jy": f * 1e-3 * (1 + rng.normal(0, .03)), "err_jy": 3e-5, "phot_ok": True})
    pd.DataFrame(ph).to_csv(proc / "spherex_phot_targets.csv", index=False)
    ucs = root / "data" / "raw" / "ultracoolsheet"
    ucs.mkdir(parents=True, exist_ok=True)
    u = obj.loc[obj.label != "star", ["name", "label"]].copy()
    u["ch2"] = 15.0
    u["ch1"] = u.ch2 + np.where(u.label == "Y", 2.5, np.where(u.label == "T", 1.2, .3)) + rng.normal(0, .2, len(u))
    u[["name", "ch1", "ch2"]].to_csv(ucs / "UltracoolSheet_-_Main.csv", index=False)
    idx = root / "CLASIFICADOR_TY" / "data" / "spherex_index"
    idx.mkdir(parents=True, exist_ok=True)
    (idx / "pilot_image_index.jsonl").write_text(json.dumps({"cloud_key": "dr1/x.fits", "target": "SYN"}) + "\n", encoding="utf-8")
    (root / "logs").mkdir(exist_ok=True)
    (root / "logs" / "run_2.status").write_text("FIN FITS completos OK (SINTETICO)\n", encoding="utf-8")
    print("sintético listo en", root, "objetos", len(obj))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
