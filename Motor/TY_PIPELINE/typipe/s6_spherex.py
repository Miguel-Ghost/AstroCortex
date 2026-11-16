"""Etapa 6: SPHEREx con los datos existentes (5 objetivos piloto).

A) Espectros e índices de banda desde la fotometría forzada ya medida
   (spherex_phot_targets): CH4 3.3 µm, H2O ~2.7 µm, CO 4.6 µm. DESCRIPTIVO: con 5
   objetos no se entrena nada; sirve para validar la extracción y para el visor.
B) Control de calidad de los 1927 MEF: cabeceras, HDU, MJD-AVG, detector, máscaras
   y estadísticas de una malla de píxeles. Los FITS se abren en solo lectura.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .common import read_json, sha256, write_json
from .data import find_table, read_table

BANDS = {  # micras: (numerador), (referencia)
    "idx_CH4_3p3": ((3.20, 3.40), (3.90, 4.15)),
    "idx_H2O_2p7": ((2.55, 2.85), (2.05, 2.30)),
    "idx_CO_4p6": ((4.50, 4.75), (3.90, 4.15)),
    "idx_pico_4um_vs_1p25": ((3.90, 4.15), (1.15, 1.35)),
}


def band_mean(wl, f, e, lo, hi):
    m = (wl >= lo) & (wl <= hi) & np.isfinite(f) & np.isfinite(e) & (e > 0)
    if m.sum() < 2:
        return np.nan, np.nan, int(m.sum())
    w = 1 / e[m] ** 2
    return float((f[m] * w).sum() / w.sum()), float(np.sqrt(1 / w.sum())), int(m.sum())


def spectra(cfg: dict, out: Path, log) -> dict:
    proc = Path(cfg["paths"]["processed"])
    try:
        ph = read_table(find_table(proc, "spherex_phot_targets"))
    except FileNotFoundError:
        return {"status": "NOT_RUN_NO_PHOTOMETRY"}
    names = {}
    try:
        st = read_table(find_table(proc, "spherex_sample_targets"))
        names = dict(zip(st["oid"], st["name"].astype(str) + " [" + st["label"].astype(str) + "]"))
    except FileNotFoundError:
        pass
    ok = ph.loc[ph["phot_ok"].astype(bool)].copy() if "phot_ok" in ph else ph.copy()
    rows = []
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig_dir = out / "espectros"
    fig_dir.mkdir(parents=True, exist_ok=True)
    for oid, g in ok.groupby("oid"):
        wl = g["wl"].to_numpy(float)
        f = g["flux_jy"].to_numpy(float) * 1e3
        e = g["err_jy"].to_numpy(float) * 1e3
        row = {"oid": int(oid), "objeto": names.get(oid, str(oid)), "n_puntos": int(len(g)),
               "wl_min": float(np.nanmin(wl)), "wl_max": float(np.nanmax(wl)),
               "snr_mediana": float(np.nanmedian(f / e))}
        for name, (num_band, ref_band) in BANDS.items():
            a, ea, na = band_mean(wl, f, e, *num_band)
            b, eb, nb = band_mean(wl, f, e, *ref_band)
            r = a / b if np.isfinite(a) and np.isfinite(b) and b != 0 else np.nan
            er = abs(r) * np.hypot(ea / a, eb / b) if np.isfinite(r) and a != 0 else np.nan
            row.update({name: r, f"{name}_err": er, f"{name}_n": f"{na}/{nb}"})
        rows.append(row)
        fig, ax = plt.subplots(figsize=(7, 3.6))
        order = np.argsort(wl)
        ax.errorbar(wl[order], f[order], yerr=e[order], fmt=".", ms=3, alpha=0.6, elinewidth=0.6)
        for lo, hi in [b[0] for b in BANDS.values()]:
            ax.axvspan(lo, hi, color="orange", alpha=0.12)
        ax.set_xlabel("λ [µm]")
        ax.set_ylabel("flujo [mJy]")
        ax.set_title(f"SPHEREx fotometría forzada — {row['objeto']}", fontsize=9)
        fig.tight_layout()
        fig.savefig(fig_dir / f"espectro_oid{int(oid)}.png", dpi=110)
        plt.close(fig)
    pd.DataFrame(rows).to_csv(out / "indices_espectrales_piloto.csv", index=False)
    log.info("SPHEREx espectros: %d objetos", len(rows))
    return {"objetos": len(rows), "filas_ok": int(len(ok)), "filas_total": int(len(ph)),
            "uso": "DESCRIPTIVO_N_PEQUENO; no entra al clasificador"}


def fits_qa(cfg: dict, out: Path, log) -> dict:
    sp = cfg["spherex"]
    if not sp.get("scan_fits_headers", True):
        return {"status": "NOT_RUN_CONFIG"}
    try:
        from astropy.io import fits
    except ImportError:
        return {"status": "NOT_RUN_DEPENDENCY_UNAVAILABLE", "falta": "astropy"}
    idx_path = Path(cfg["paths"]["spherex_index"])
    raw = Path(cfg["paths"]["spherex_raw"])
    if not idx_path.is_file() or not raw.is_dir():
        return {"status": "NOT_RUN_NO_FITS"}
    with idx_path.open(encoding="utf-8") as fh:
        index = [json.loads(l) for l in fh if l.strip()][: int(sp["max_fits"])]
    stride = int(sp["fits_sample_stride"])
    cache = out / "fits_qa_parcial.jsonl"
    done = {}
    if cache.is_file():
        with cache.open(encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                done[r["cloud_key"]] = r
    with cache.open("a", encoding="utf-8") as fh:
        for n, item in enumerate(index):
            key = item["cloud_key"]
            if key in done:
                continue
            path = raw / key
            r = {"cloud_key": key, "target": item.get("target"), "collection": item.get("collection"),
                 "detector": item.get("detector")}
            if not path.is_file():
                r["status"] = "MISSING"
            else:
                try:
                    r["bytes"] = path.stat().st_size
                    if sp.get("verify_fits_sha256"):
                        rec = path.with_name(path.name + ".json")
                        r["sha_ok"] = rec.is_file() and read_json(rec).get("sha256") == sha256(path)
                    with fits.open(path, memmap=True, lazy_load_hdus=True) as h:
                        names = [x.name for x in h]
                        img = h["IMAGE"]
                        hdr = img.header
                        r.update({"hdus": ",".join(names), "mjd_avg": hdr.get("MJD-AVG", h[0].header.get("MJD-AVG")),
                                  "bunit": hdr.get("BUNIT"), "shape": list(img.shape)})
                        s = np.asarray(img.data[::stride, ::stride], dtype=float)
                        good = s[np.isfinite(s)]
                        r.update({"img_mediana": float(np.median(good)) if good.size else None,
                                  "img_p05": float(np.quantile(good, .05)) if good.size else None,
                                  "img_p95": float(np.quantile(good, .95)) if good.size else None,
                                  "frac_nan": float(1 - good.size / max(s.size, 1))})
                        if "ZODI" in names:
                            z = np.asarray(h["ZODI"].data[::stride, ::stride], dtype=float)
                            r["zodi_mediana"] = float(np.nanmedian(z))
                        if "FLAGS" in names:
                            fh_ = h["FLAGS"].header
                            r["n_mask_defs"] = sum(1 for k in fh_ if str(k).startswith("MSKN"))
                            fl = np.asarray(h["FLAGS"].data[::stride, ::stride]).astype(np.int64)
                            r["frac_flagged_any"] = float((fl != 0).mean())
                    r["status"] = "OK"
                except Exception as exc:  # se registra y se sigue
                    r["status"] = "ERROR"
                    r["error"] = repr(exc)[:300]
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            if n % 200 == 0:
                log.info("FITS QA %d/%d", n, len(index))
    rows = []
    with cache.open(encoding="utf-8") as fh:
        rows = [json.loads(l) for l in fh if l.strip()]
    df = pd.DataFrame(rows).drop_duplicates("cloud_key", keep="last")
    df.to_csv(out / "fits_qa.csv", index=False)
    by = df.groupby(["target", "status"]).size().unstack(fill_value=0).to_dict(orient="index")
    return {"status": "OK", "archivos": int(len(df)), "por_objetivo_estado": by,
            "errores": int((df["status"] == "ERROR").sum()), "faltantes": int((df["status"] == "MISSING").sum())}


def run(cfg: dict, out: Path, log) -> dict:
    a = spectra(cfg, out, log)
    b = fits_qa(cfg, out, log)
    warnings = []
    if b.get("status") == "OK" and (b["errores"] or b["faltantes"]):
        warnings.append(f"FITS QA: {b['errores']} errores, {b['faltantes']} faltantes")
    write_json(out / "spherex_resumen.json", {"espectros": a, "fits_qa": b})
    return {"summary": {"espectros": a, "fits_qa": {k: v for k, v in b.items() if k != "por_objetivo_estado"}},
            "warnings": warnings}
