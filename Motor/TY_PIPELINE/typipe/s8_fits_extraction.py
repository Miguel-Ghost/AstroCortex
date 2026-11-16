"""Etapa 'extracción FITS': usa TODOS los MEF (1927) de los objetivos piloto.

Por cada exposición:
1. Posición predicha a MJD-AVG: movimiento propio (apply_space_motion) + PARALAJE ANUAL
   (posición de la Tierra respecto del baricentro; SPHEREx está en órbita baja, su
   desplazamiento respecto del geocentro es despreciable frente al píxel de 6.2").
2. Recorte (2·HALF+1)² de IMAGE, VARIANCE, FLAGS y ZODI; IMAGE − ZODI.
3. Máscara desde la propia cabecera (MSKN/MSKM): todo salvo SOURCE.
4. Fondo por mediana en anillo; ajuste de gaussiana 2D ponderada (posición, σ, amplitud)
   con errores de la matriz de covarianza. SPHEREx está submuestreado (FWHM≈1.1 px): la
   gaussiana es una aproximación; el resultado se marca DEGRADED_GAUSS_NO_EPSF.
5. Fotometría de apertura (r=2 px) en Jy y longitud de onda central del píxel (WCS 'W' sin SIP).
Por objetivo: trayectoria (posiciones vs tiempo), ajuste de movimiento propio y comparación
con el catálogo; espectro con todas las exposiciones.
"""
from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from .common import write_json
from .data import find_table, read_table

HALF = 7


def flag_defs(hdr) -> dict:
    defs = {}
    for k in hdr:
        if str(k).startswith("MSKN"):
            n = str(k)[4:]
            name = str(hdr[k]).strip()
            v = hdr.get(f"MSKM{n}")
            try:
                v = int(v) if v is not None else 1 << int(n)
            except (TypeError, ValueError):
                v = 1 << int(n)
            defs[name] = v
    return defs


def parallax_offset(ra_deg, dec_deg, plx_mas, mjd):
    """Desplazamiento por paralaje anual (Δα·cosδ, Δδ) en mas, observador geocéntrico."""
    from astropy.coordinates import get_body_barycentric
    from astropy.time import Time
    if not np.isfinite(plx_mas) or plx_mas <= 0:
        return 0.0, 0.0
    e = get_body_barycentric("earth", Time(mjd, format="mjd", scale="tdb"))
    X, Y, Z = (float(v) for v in e.xyz.to("AU").value)
    a, d = math.radians(ra_deg), math.radians(dec_deg)
    da = plx_mas * (X * math.sin(a) - Y * math.cos(a))
    dd = plx_mas * (X * math.cos(a) * math.sin(d) + Y * math.sin(a) * math.sin(d) - Z * math.cos(d))
    return da, dd


def predict(row, mjd):
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astropy.time import Time
    c = SkyCoord(ra=float(row["ra"]) * u.deg, dec=float(row["dec"]) * u.deg,
                 pm_ra_cosdec=float(np.nan_to_num(row["pmra"])) * u.mas / u.yr,
                 pm_dec=float(np.nan_to_num(row["pmdec"])) * u.mas / u.yr,
                 obstime=Time(float(row["epoch"]), format="jyear"), frame="icrs")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = c.apply_space_motion(new_obstime=Time(mjd, format="mjd"))
    da, dd = parallax_offset(m.ra.deg, m.dec.deg, float(row.get("plx", np.nan)), mjd)
    ra = m.ra.deg + da / 3.6e6 / math.cos(math.radians(m.dec.deg))
    dec = m.dec.deg + dd / 3.6e6
    return ra, dec, m.ra.deg, m.dec.deg


def gauss_fit(img, var, good, x0, y0):
    from scipy.optimize import least_squares
    yy, xx = np.indices(img.shape)
    m = good & np.isfinite(img) & np.isfinite(var) & (var > 0)
    if m.sum() < 12:
        return None
    w = 1 / np.sqrt(var[m])
    amp0 = max(float(np.nanmax(img[m])), 1e-6)

    def resid(p):
        a, x, y, s, c = p
        model = a * np.exp(-((xx[m] - x) ** 2 + (yy[m] - y) ** 2) / (2 * s * s)) + c
        return (img[m] - model) * w

    p0 = [amp0, x0, y0, 0.8, 0.0]
    lo = [0, x0 - 3, y0 - 3, 0.3, -np.inf]
    hi = [np.inf, x0 + 3, y0 + 3, 3.0, np.inf]
    try:
        r = least_squares(resid, p0, bounds=(lo, hi), x_scale="jac")
    except Exception:
        return None
    dof = max(int(m.sum()) - 5, 1)
    chi2 = float(np.sum(r.fun ** 2))
    try:
        cov = np.linalg.inv(r.jac.T @ r.jac) * max(chi2 / dof, 1.0)
        err = np.sqrt(np.clip(np.diag(cov), 0, np.inf))
    except np.linalg.LinAlgError:
        err = np.full(5, np.nan)
    a, x, y, s, c = r.x
    return {"amp": a, "x": x, "y": y, "sigma": s, "const": c, "ex": err[1], "ey": err[2],
            "amp_snr": a / err[0] if err[0] > 0 else np.nan, "chi2_red": chi2 / dof, "ok": bool(r.success)}


def extract_one(path: Path, row) -> dict:
    from astropy.io import fits
    from astropy.wcs import WCS
    from astropy.wcs.utils import proj_plane_pixel_area
    out = {}
    with fits.open(path, memmap=True, lazy_load_hdus=True) as h:
        hdr = h["IMAGE"].header
        mjd = float(hdr.get("MJD-AVG") or h[0].header.get("MJD-AVG"))
        ra_p, dec_p, ra_pm, dec_pm = predict(row, mjd)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wcs = WCS(hdr).celestial
        x, y = (float(v) for v in wcs.world_to_pixel_values(ra_p, dec_p))
        ny, nx = h["IMAGE"].shape
        out.update({"mjd": mjd, "ra_pred": ra_p, "dec_pred": dec_p, "x_pred": x, "y_pred": y,
                    "detector": hdr.get("DETECTOR")})
        xc, yc = int(round(x)), int(round(y))
        if xc - HALF < 0 or yc - HALF < 0 or xc + HALF >= nx or yc + HALF >= ny:
            out["status"] = "BORDE_O_FUERA"
            return out
        sl = (slice(yc - HALF, yc + HALF + 1), slice(xc - HALF, xc + HALF + 1))
        img = np.asarray(h["IMAGE"].data[sl], float) - np.asarray(h["ZODI"].data[sl], float)
        var = np.asarray(h["VARIANCE"].data[sl], float)
        flg = np.asarray(h["FLAGS"].data[sl]).astype(np.int64)
        defs = flag_defs(h["FLAGS"].header)
        bad_bits = 0
        for name, v in defs.items():
            if name.upper() != "SOURCE":
                bad_bits |= int(v)
        good = np.isfinite(img) & np.isfinite(var) & ((flg & bad_bits) == 0)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ww = WCS(hdr, fobj=h, key="W")
                ww.sip = None
                wl, bw = (float(np.asarray(v)) for v in ww.pixel_to_world_values(x, y))
        except Exception:
            wl, bw = np.nan, np.nan
        omega = float(proj_plane_pixel_area(wcs)) * (math.pi / 180) ** 2
    yy, xx = np.indices(img.shape)
    lx, ly = x - (xc - HALF), y - (yc - HALF)
    rr = np.hypot(xx - lx, yy - ly)
    ann = good & (rr >= 4.5) & (rr <= HALF)
    core = rr <= 2.0
    out.update({"wl_um": wl, "bw_um": bw, "n_bad_core": int((core & ~good).sum()),
                "bad_names_core": ",".join(sorted(n for n, v in defs.items()
                                                  if n.upper() != "SOURCE" and ((flg[core] & int(v)) != 0).any()))})
    if ann.sum() < 10:
        out["status"] = "SIN_FONDO"
        return out
    bkg = float(np.median(img[ann]))
    sub = img - bkg
    apg = core & good
    k = 1e6 * omega
    out.update({"bkg_mjysr": bkg, "flux_jy": float(sub[apg].sum() * k),
                "err_jy": float(np.sqrt(var[apg].sum()) * k) if apg.any() else np.nan})
    out["snr_ap"] = out["flux_jy"] / out["err_jy"] if out["err_jy"] and out["err_jy"] > 0 else np.nan
    fit = gauss_fit(sub, var, good, lx, ly)
    if fit is None:
        out["status"] = "AJUSTE_FALLIDO"
        return out
    xf, yf = fit["x"] + (xc - HALF), fit["y"] + (yc - HALF)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ra_f, dec_f = (float(v) for v in wcs.pixel_to_world_values(xf, yf))
    scale = math.sqrt(omega) * 206264.806  # arcsec por píxel
    cosd = math.cos(math.radians(dec_p))
    out.update({"x_fit": xf, "y_fit": yf, "ra_fit": ra_f, "dec_fit": dec_f,
                "dra_cosd_arcsec": (ra_f - ra_p) * cosd * 3600, "ddec_arcsec": (dec_f - dec_p) * 3600,
                "epos_arcsec": float(np.hypot(fit["ex"], fit["ey"]) * scale), "pix_arcsec": scale,
                "sigma_px": fit["sigma"], "amp_snr": fit["amp_snr"], "chi2_red": fit["chi2_red"],
                "fit_ok": fit["ok"], "status": "OK_DEGRADED_GAUSS_NO_EPSF"})
    return out


def fit_motion(d: pd.DataFrame, row) -> dict:
    """Ajuste lineal ponderado de los residuos de posición vs tiempo.
    Pendiente ≈ corrección al movimiento propio del catálogo; con recorte 3σ iterativo."""
    t = (d["mjd"].to_numpy() - d["mjd"].mean()) / 365.25
    res = {}
    for col, name in (("dra_cosd_arcsec", "pmra"), ("ddec_arcsec", "pmdec")):
        v = d[col].to_numpy()
        e = np.maximum(d["epos_arcsec"].to_numpy() / math.sqrt(2), 0.05)
        keep = np.isfinite(v) & np.isfinite(e)
        for _ in range(5):
            if keep.sum() < 8:
                break
            W = 1 / e[keep] ** 2
            A = np.vstack([np.ones(keep.sum()), t[keep]]).T
            cov = np.linalg.inv(A.T @ (A * W[:, None]))
            beta = cov @ (A.T @ (W * v[keep]))
            r = (v - (beta[0] + beta[1] * t)) / e
            new = keep & (np.abs(r) < 3)
            if new.sum() == keep.sum():
                break
            keep = new
        if keep.sum() >= 8:
            chi2r = float(np.sum(r[keep] ** 2) / max(keep.sum() - 2, 1))
            s = math.sqrt(max(chi2r, 1.0))
            res[name] = {"delta_mas_yr": float(beta[1] * 1000), "err_mas_yr": float(math.sqrt(cov[1, 1]) * s * 1000),
                         "catalogo_mas_yr": float(row[name]), "medido_mas_yr": float(row[name] + beta[1] * 1000),
                         "offset_medio_arcsec": float(beta[0]), "n": int(keep.sum()), "chi2_red": chi2r}
    return res


def run(cfg: dict, out: Path, log) -> dict:
    try:
        import astropy  # noqa: F401
        import scipy  # noqa: F401
    except ImportError as exc:
        return {"summary": {"status": "NOT_RUN_DEPENDENCY_UNAVAILABLE", "falta": str(exc)},
                "warnings": [f"NOT_RUN_DEPENDENCY_UNAVAILABLE: {exc}"]}
    proc = Path(cfg["paths"]["processed"])
    targets = read_table(find_table(proc, "targets"))
    idx_path = Path(cfg["paths"]["spherex_index"])
    raw = Path(cfg["paths"]["spherex_raw"])
    with idx_path.open(encoding="utf-8") as fh:
        index = [json.loads(l) for l in fh if l.strip()]
    cache = out / "extraccion_por_exposicion.jsonl"
    done = set()
    if cache.is_file():
        with cache.open(encoding="utf-8") as fh:
            done = {json.loads(l)["cloud_key"] for l in fh if l.strip()}
    with cache.open("a", encoding="utf-8") as fh:
        for n, item in enumerate(index):
            if item["cloud_key"] in done:
                continue
            row = targets.iloc[int(item["target_index"])]
            rec = {"cloud_key": item["cloud_key"], "target": str(row["target"]), "collection": item.get("collection")}
            path = raw / item["cloud_key"]
            if not path.is_file():
                rec["status"] = "FALTA_FITS"
            else:
                try:
                    rec.update(extract_one(path, row))
                except Exception as exc:
                    rec.update({"status": "ERROR", "error": repr(exc)[:300]})
            fh.write(json.dumps(rec, ensure_ascii=False, default=float) + "\n")
            fh.flush()
            if n % 100 == 0:
                log.info("extracción FITS %d/%d", n, len(index))
    with cache.open(encoding="utf-8") as fh:
        df = pd.DataFrame([json.loads(l) for l in fh if l.strip()]).drop_duplicates("cloud_key", keep="last")
    df.to_csv(out / "extraccion_por_exposicion.csv", index=False)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig_dir = out / "figuras"
    fig_dir.mkdir(exist_ok=True)
    per_target = {}
    for name, g in df.groupby("target"):
        row = targets.loc[targets["target"].astype(str) == name].iloc[0]
        ok = g[g["status"].astype(str).str.startswith("OK")].copy()
        clean = ok[(ok["n_bad_core"] == 0) & (ok["amp_snr"] > 5) & ok["fit_ok"].astype(bool)
                   & (ok["sigma_px"].between(0.35, 2.5))]
        info = {"exposiciones": int(len(g)), "estados": g["status"].value_counts().to_dict(),
                "limpias_para_astrometria": int(len(clean)),
                "mjd_rango": [float(g["mjd"].min()), float(g["mjd"].max())] if g["mjd"].notna().any() else None,
                "pm_catalogo_mas_yr": [float(row["pmra"]), float(row["pmdec"])], "plx_catalogo_mas": float(row["plx"])}
        if len(clean) >= 8:
            info["movimiento_propio"] = fit_motion(clean, row)
            info["residuo_mediano_arcsec"] = float(np.median(np.hypot(clean["dra_cosd_arcsec"], clean["ddec_arcsec"])))
            fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
            t = clean["mjd"]
            for a, col, lab in ((ax[0], "dra_cosd_arcsec", "Δα·cosδ [″]"), (ax[1], "ddec_arcsec", "Δδ [″]")):
                a.errorbar(t, clean[col], yerr=clean["epos_arcsec"] / math.sqrt(2), fmt=".", ms=3, alpha=.6)
                a.axhline(0, color="k", lw=.8)
                a.set_xlabel("MJD")
                a.set_ylabel(lab + " medido − predicho")
            fig.suptitle(f"{name}: residuos de trayectoria (predicción con μ y paralaje de catálogo)", fontsize=9)
            fig.tight_layout()
            fig.savefig(fig_dir / f"trayectoria_{name.replace(' ', '_').replace(chr(39), '')}.png", dpi=110)
            plt.close(fig)
        phot = ok[(ok["n_bad_core"] == 0) & np.isfinite(ok["wl_um"])]
        if len(phot) >= 5:
            fig, ax = plt.subplots(figsize=(7, 3.6))
            ax.errorbar(phot["wl_um"], phot["flux_jy"] * 1e3, yerr=phot["err_jy"] * 1e3, fmt=".", ms=3, alpha=.5)
            ax.set_xlabel("λ [µm]")
            ax.set_ylabel("flujo [mJy] (apertura r=2 px)")
            ax.set_title(f"{name}: espectro con {len(phot)} exposiciones", fontsize=9)
            fig.tight_layout()
            fig.savefig(fig_dir / f"espectro_{name.replace(' ', '_').replace(chr(39), '')}.png", dpi=110)
            plt.close(fig)
            info["exposiciones_con_fotometria_limpia"] = int(len(phot))
        per_target[name] = info
        log.info("%s: %s", name, {k: v for k, v in info.items() if k != "estados"})
    write_json(out / "trayectorias_y_movimiento_propio.json", {
        "metodo": "gaussiana 2D ponderada sobre IMAGE−ZODI; predicción con μ + paralaje anual geocéntrico",
        "estado": "DEGRADED_GAUSS_NO_EPSF: posiciones aproximadas; validar con ePSF del motor",
        "objetivos": per_target})
    warnings_ = [f"{k}: {v['estados']}" for k, v in per_target.items()
                 if v["estados"].get("ERROR", 0) or v["estados"].get("FALTA_FITS", 0)]
    return {"summary": {"exposiciones": int(len(df)), "estados": df["status"].value_counts().to_dict(),
                        "objetivos": {k: {kk: v.get(kk) for kk in ("limpias_para_astrometria",
                                                                     "exposiciones_con_fotometria_limpia")}
                                      for k, v in per_target.items()}},
            "warnings": warnings_}
