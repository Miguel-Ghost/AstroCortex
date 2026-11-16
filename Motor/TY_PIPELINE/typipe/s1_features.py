"""Etapa 1: tabla de características por objeto, con la misma procedencia para todas las clases.

Reglas antiatajos:
- Solo se usan mediciones obtenidas igual para todas las clases (CatWISE, AllWISE,
  2MASS y unWISE consultados por posición; Gaia por source_id solo en un grupo aparte).
- Las magnitudes aparentes, SNR, separaciones de cruce y "tiene/no tiene catálogo"
  quedan en grupos de AUDITORÍA: sirven para medir atajos, no para el modelo principal.
- Los límites superiores (ph_qual U) y los artefactos (cc_flags) se convierten en NaN
  con la misma regla para todas las clases.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .common import write_json, utc
from .data import OBJECTS_FORBIDDEN, best_match, load_catalog, load_gaia, load_objects

PREFIX = {"catwise": "cw", "allwise": "aw", "tmass": "tm", "unwise": "uw"}
KEEP = {
    "catwise": ["w1mpro", "w1sigmpro", "w2mpro", "w2sigmpro", "pmra", "pmdec",
                "cc_flags", "ab_flags", "w1snr", "w2snr"],
    "allwise": ["w1mpro", "w1sigmpro", "w2mpro", "w2sigmpro", "cc_flags", "ph_qual",
                "var_flg", "nb", "na", "ext_flg"],
    "tmass": ["j_m", "j_msigcom", "h_m", "h_msigcom", "k_m", "k_msigcom", "ph_qual",
              "cc_flg", "rd_flg", "bl_flg"],
    "unwise": ["flux_w1", "dflux_w1", "flux_w2", "dflux_w2", "qf_w1", "qf_w2",
               "fracflux_w1", "fracflux_w2", "flags_unwise_w1", "flags_unwise_w2", "primary"],
}


def save_table(df: pd.DataFrame, path_stem: Path) -> Path:
    try:
        import pyarrow  # noqa: F401
        p = path_stem.with_suffix(".parquet")
        df.to_parquet(p, index=False)
    except ImportError:
        p = path_stem.with_suffix(".csv")
        df.to_csv(p, index=False)
    return p


def load_saved(path_stem: Path) -> pd.DataFrame:
    for ext in (".parquet", ".csv"):
        p = path_stem.with_suffix(ext)
        if p.is_file():
            return pd.read_parquet(p) if ext == ".parquet" else pd.read_csv(p, low_memory=False)
    raise FileNotFoundError(path_stem)


def num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan)


def char_at(s: pd.Series, i: int) -> pd.Series:
    return s.astype("string").str.strip().str[i]


def galactic_latitude(ra_deg, dec_deg) -> np.ndarray:
    ra, dec = np.deg2rad(ra_deg), np.deg2rad(dec_deg)
    # Polo galáctico norte (ICRS) y rotación estándar.
    ra_gp, dec_gp = np.deg2rad(192.85948), np.deg2rad(27.12825)
    sinb = np.sin(dec) * np.sin(dec_gp) + np.cos(dec) * np.cos(dec_gp) * np.cos(ra - ra_gp)
    return np.rad2deg(np.arcsin(np.clip(sinb, -1, 1)))


def riello_cstar(excess, bp_rp):
    x = bp_rp
    corr = np.select([x < 0.5, x < 4.0],
                     [1.154360 + 0.033772 * x + 0.032277 * x ** 2,
                      1.162004 + 0.011464 * x + 0.049255 * x ** 2 - 0.005879 * x ** 3],
                     default=1.057572 + 0.140537 * x)
    return pd.Series(np.where(np.isfinite(x), excess - corr, np.nan), index=excess.index)


def run(cfg: dict, out: Path, log) -> dict:
    objects, objects_sha = load_objects(cfg)
    radius = float(cfg["match_radius_arcsec"])
    mask = bool(cfg["quality"]["mask_artifact_photometry"])
    floor = float(cfg["quality"]["mu_floor_arcsec_yr"])
    t = objects[["oid", "label", "ra", "dec"]].copy()
    t["glat"] = galactic_latitude(t["ra"].to_numpy(float), t["dec"].to_numpy(float))
    match_info = {}

    for name in cfg["catalogs"]:
        frame, info = load_catalog(cfg, name, objects_sha)
        best = best_match(frame, radius)
        p = PREFIX[name]
        cols = [c for c in KEEP[name] if c in best.columns]
        sub = best[["oid", "sep_arcsec", "n_cand", "sep2"] + cols].copy()
        sub.columns = ["oid"] + [f"{p}_{c}" for c in sub.columns[1:]]
        t = t.merge(sub, on="oid", how="left", validate="one_to_one")
        t[f"{p}_n_cand"] = t[f"{p}_n_cand"].fillna(0).astype(int)
        t[f"has_{p}"] = t[f"{p}_n_cand"] > 0
        info.update({"matched": int(t[f"has_{p}"].sum()),
                     "ambiguous": int((t[f"{p}_n_cand"] > 1).sum())})
        match_info[name] = info
        log.info("%s: %s", name, info)

    qa = {}
    # ---- Limpieza con la misma regla para todas las clases ----
    if mask:
        for band, i in (("w1", 0), ("w2", 1)):
            bad = (char_at(t["cw_cc_flags"], i).fillna("0") != "0") | \
                  (char_at(t["cw_ab_flags"], i).fillna("0") != "0")
            qa[f"cw_{band}_artifact"] = int(bad.sum())
            t.loc[bad, [f"cw_{band}mpro", f"cw_{band}sigmpro"]] = np.nan
            bad = ((char_at(t["aw_cc_flags"], i).fillna("0") != "0") |
                   char_at(t["aw_ph_qual"], i).isin(["U", "X"]).fillna(False))
            qa[f"aw_{band}_bad_or_upper"] = int(bad.sum())
            t.loc[bad, [f"aw_{band}mpro", f"aw_{band}sigmpro"]] = np.nan
        for band, i in (("j", 0), ("h", 1), ("k", 2)):
            bad = (char_at(t["tm_ph_qual"], i).isin(["U", "X", "E", "F"]).fillna(False) |
                   (char_at(t["tm_cc_flg"], i).fillna("0") != "0"))
            qa[f"tm_{band}_bad_or_upper"] = int(bad.sum())
            sig = "k_msigcom" if band == "k" else f"{band}_msigcom"
            t.loc[bad, [f"tm_{band}_m", f"tm_{sig}"]] = np.nan
        for band in ("w1", "w2"):
            bad = (num(t[f"uw_flags_unwise_{band}"]).fillna(0) != 0) | (num(t[f"uw_flux_{band}"]) <= 0)
            qa[f"uw_{band}_flagged_or_nonpositive"] = int(bad.sum())
            t.loc[bad, [f"uw_flux_{band}", f"uw_dflux_{band}"]] = np.nan

    W1, W2 = num(t["cw_w1mpro"]), num(t["cw_w2mpro"])
    J, H, K = num(t["tm_j_m"]), num(t["tm_h_m"]), num(t["tm_k_m"])
    f1, f2 = num(t["uw_flux_w1"]), num(t["uw_flux_w2"])
    mu = np.hypot(num(t["cw_pmra"]), num(t["cw_pmdec"]))  # CatWISE: arcsec/año
    mu_c = mu.clip(lower=floor)

    d = {}
    d["cw_W1_W2"] = W1 - W2
    d["aw_W1_W2"] = num(t["aw_w1mpro"]) - num(t["aw_w2mpro"])
    d["uw_W1_W2"] = -2.5 * np.log10(f1 / f2)
    d["cw_W1_W2_err"] = np.hypot(num(t["cw_w1sigmpro"]), num(t["cw_w2sigmpro"]))
    d["J_H"] = J - H
    d["H_Ks"] = H - K
    d["J_Ks"] = J - K
    d["J_W1"] = J - W1
    d["J_W2"] = J - W2
    d["H_W2"] = H - W2
    d["Ks_W2"] = K - W2
    d["cw_mu"] = mu
    d["cw_log_mu"] = np.log10(mu_c)
    d["Hrpm_W2"] = W2 + 5 * np.log10(mu_c) + 5
    d["Hrpm_J"] = J + 5 * np.log10(mu_c) + 5
    d["aw_var_w2"] = num(char_at(t["aw_var_flg"], 1).replace("n", pd.NA))
    for k, v in d.items():
        t[k] = v

    # ---- Columnas complementarias (typipe.fetch_extra): CatWISE *_pm, σμ, paralaje WISE; AllWISE W3/W4 ----
    extra_info = {}
    extra_root = Path(cfg["paths"].get("extra_catalogs", ""))
    for name, p in (("catwise_full", "cwx"), ("allwise_full", "awx")):
        if not (extra_root / name).is_dir():
            extra_info[name] = "NO_DISPONIBLE"
            continue
        try:
            frame, info = load_catalog(cfg, name, objects_sha, extra=True)
        except Exception as exc:
            extra_info[name] = f"ERROR: {exc!r}"[:300]
            continue
        best = best_match(frame, radius)
        want = {"cwx": ["w1mpro_pm", "w1sigmpro_pm", "w2mpro_pm", "w2sigmpro_pm", "sigpmra", "sigpmdec",
                        "par_pm", "par_pmsig", "pmra", "pmdec", "w1rchi2_pm", "w2rchi2_pm", "nb", "na"],
                "awx": ["w3mpro", "w3sigmpro", "w3snr", "w4mpro", "w4sigmpro", "w4snr", "ph_qual", "cc_flags",
                        "w1mpro", "w2mpro", "ext_flg"]}[p]
        cols = [c for c in want if c in best.columns]
        sub = best[["oid"] + cols].copy()
        sub.columns = ["oid"] + [f"{p}_{c}" for c in cols]
        t = t.merge(sub, on="oid", how="left", validate="one_to_one")
        extra_info[name] = {**info, "columnas": cols, "faltan": [c for c in want if c not in cols]}
        log.info("%s: %s", name, extra_info[name])
    if "awx_w3mpro" in t.columns:
        w3_ok = char_at(t["awx_ph_qual"], 2).isin(["A", "B", "C"]).fillna(False) & \
                (char_at(t["awx_cc_flags"], 2).fillna("0") == "0")
        W3 = num(t["awx_w3mpro"]).where(w3_ok)
        t["W2_W3"] = num(t["awx_w2mpro"]) - W3
        t["W1_W3"] = num(t["awx_w1mpro"]) - W3
        t["W3_detectada"] = w3_ok.astype(int)
    if "cwx_w2mpro_pm" in t.columns:
        W1p, W2p = num(t["cwx_w1mpro_pm"]), num(t["cwx_w2mpro_pm"])
        if mask:
            bad1 = (char_at(t["cw_cc_flags"], 0).fillna("0") != "0") | (char_at(t["cw_ab_flags"], 0).fillna("0") != "0")
            bad2 = (char_at(t["cw_cc_flags"], 1).fillna("0") != "0") | (char_at(t["cw_ab_flags"], 1).fillna("0") != "0")
            W1p, W2p = W1p.where(~bad1), W2p.where(~bad2)
        mux = np.hypot(num(t["cwx_pmra"]), num(t["cwx_pmdec"]))
        smu = np.hypot(num(t["cwx_sigpmra"]), num(t["cwx_sigpmdec"])) / np.sqrt(2)
        t["cw_W1_W2_pm"] = W1p - W2p
        t["cw_mu_snr"] = mux / smu
        t["Hrpm_W2_pm"] = W2p + 5 * np.log10(mux.clip(lower=floor)) + 5
        if "cwx_par_pm" in t.columns:
            t["cw_par"] = num(t["cwx_par_pm"])
            t["cw_par_snr"] = num(t["cwx_par_pm"]) / num(t["cwx_par_pmsig"])

    gaia = load_gaia(cfg)
    gaia_cols = []
    if gaia is not None:
        g = gaia.set_index("oid")
        G = num(g["phot_g_mean_mag"])
        BP, RP = num(g["phot_bp_mean_mag"]), num(g["phot_rp_mean_mag"])
        plx, eplx = num(g["parallax"]), num(g["parallax_error"])
        gd = pd.DataFrame(index=g.index)
        gd["gaia_parallax"] = plx
        gd["gaia_plx_snr"] = plx / eplx
        gd["gaia_ruwe"] = num(g.get("ruwe"))
        gd["gaia_BP_RP"] = BP - RP
        gd["gaia_Cstar"] = riello_cstar(num(g["phot_bp_rp_excess_factor"]), (BP - RP).to_numpy())
        gd["gaia_mu"] = np.hypot(num(g["pmra"]), num(g["pmdec"])) / 1000.0
        gd["gaia_G"] = G
        t = t.merge(gd.reset_index(), on="oid", how="left", validate="one_to_one")
        t["has_gaia"] = t["gaia_G"].notna()
        t["gaia_G_W2"] = t["gaia_G"] - W2
        t["gaia_G_J"] = t["gaia_G"] - J
        good_plx = t["gaia_plx_snr"] > 5
        t["gaia_M_W2"] = np.where(good_plx, W2 + 5 * np.log10(t["gaia_parallax"] / 1000.0) + 5, np.nan)
        gaia_cols = ["gaia_parallax", "gaia_plx_snr", "gaia_ruwe", "gaia_BP_RP", "gaia_Cstar",
                     "gaia_mu", "gaia_G_W2", "gaia_G_J", "gaia_M_W2"]

    groups = {
        "color_wise": ["cw_W1_W2", "aw_W1_W2", "uw_W1_W2"],
        "color_2mass": ["J_H", "H_Ks", "J_Ks"],
        "color_nir_mir": ["J_W1", "J_W2", "H_W2", "Ks_W2"],
        "movimiento": ["cw_mu", "cw_log_mu", "Hrpm_W2", "Hrpm_J"],
        "variabilidad": ["aw_var_w2"],
        "color_w3": ["W2_W3", "W1_W3", "W3_detectada"],
        "wise_pm": ["cw_W1_W2_pm", "cw_mu_snr", "Hrpm_W2_pm"],
        "paralaje_wise": ["cw_par", "cw_par_snr"],
        "gaia": gaia_cols,
        "AUDIT_brillo": ["cw_w1mpro", "cw_w2mpro", "tm_j_m", "cw_w2snr", "cw_W1_W2_err"],
        "AUDIT_artefacto": ([f"has_{PREFIX[c]}" for c in cfg["catalogs"]] +
                            [f"{PREFIX[c]}_n_cand" for c in cfg["catalogs"]] +
                            [f"{PREFIX[c]}_sep_arcsec" for c in cfg["catalogs"]] +
                            (["has_gaia"] if gaia is not None else [])),
        "AUDIT_posicion": ["glat"],
    }
    feature_sets = {
        "E1_nucleo_fisico": ["color_wise", "color_2mass", "color_nir_mir", "movimiento", "variabilidad",
                             "color_w3", "wise_pm"],
        "E1b_sin_extra": ["color_wise", "color_2mass", "color_nir_mir", "movimiento", "variabilidad"],
        "E1c_mas_paralaje_wise": ["color_wise", "color_2mass", "color_nir_mir", "movimiento", "variabilidad",
                                  "color_w3", "wise_pm", "paralaje_wise"],
        "E2_nucleo_mas_gaia": ["color_wise", "color_2mass", "color_nir_mir", "movimiento",
                               "variabilidad", "color_w3", "wise_pm", "gaia"],
        "E3_nucleo_mas_brillo": ["color_wise", "color_2mass", "color_nir_mir", "movimiento",
                                 "variabilidad", "AUDIT_brillo"],
        "E0_solo_atajos": ["AUDIT_artefacto", "AUDIT_posicion", "AUDIT_brillo"],
    }
    for k in list(groups):
        groups[k] = [c for c in groups[k] if c in t.columns]
    for c in groups["AUDIT_artefacto"]:
        if t[c].dtype == bool:
            t[c] = t[c].astype(int)

    path = save_table(t, out / "features")
    dictionary = []
    formulas = {
        "cw_W1_W2": "CatWISE w1mpro − w2mpro [mag Vega]",
        "aw_W1_W2": "AllWISE w1mpro − w2mpro (sin límites U) [mag Vega]",
        "uw_W1_W2": "−2.5 log10(flux_w1/flux_w2) unWISE [mag Vega]",
        "J_W2": "2MASS J − CatWISE W2 [mag Vega; épocas distintas]",
        "cw_mu": "hypot(pmra, pmdec) CatWISE [arcsec/año]",
        "Hrpm_W2": "W2 + 5 log10(max(μ, piso)) + 5 [mag]; movimiento propio reducido",
        "Hrpm_J": "J + 5 log10(max(μ, piso)) + 5 [mag]",
        "gaia_Cstar": "exceso BP/RP corregido (Riello+2021) [adim.]",
        "gaia_M_W2": "W2 + 5 log10(ϖ/1000) + 5, solo ϖ/σ>5 [mag]",
        "W2_W3": "AllWISE w2mpro − w3mpro, W3 solo con ph_qual A/B/C y cc_flags 0 [mag Vega]",
        "W1_W3": "AllWISE w1mpro − w3mpro, misma regla [mag Vega]",
        "cw_W1_W2_pm": "CatWISE w1mpro_pm − w2mpro_pm (ajuste con movimiento) [mag Vega]",
        "cw_mu_snr": "μ / σμ CatWISE [adim.]",
        "Hrpm_W2_pm": "w2mpro_pm + 5 log10(max(μ, piso)) + 5 [mag]",
        "cw_par": "paralaje CatWISE par_pm [arcsec]; señal débil, grupo aparte",
        "cw_par_snr": "par_pm / par_pmsig [adim.]",
    }
    role = {g: ("PREDICTOR" if not g.startswith("AUDIT") else "SOLO_AUDITORIA") for g in groups}
    for g, cols in groups.items():
        for c in cols:
            dictionary.append({"columna": c, "grupo": g, "rol": role[g],
                               "formula": formulas.get(c), "cobertura": float(t[c].notna().mean())})
    for c, why in OBJECTS_FORBIDDEN.items():
        dictionary.append({"columna": c, "grupo": "objects.parquet", "rol": "PROHIBIDO", "motivo": why})
    write_json(out / "feature_groups.json", {"groups": groups, "feature_sets": feature_sets,
                                             "generated_utc": utc()})
    write_json(out / "diccionario_variables.json", dictionary)
    write_json(out / "calidad_cruces.json", {"match": match_info, "quality_masks": qa, "extra": extra_info,
                                             "radius_arcsec": radius})
    cov = t.groupby("label")[[c for g in ("color_wise", "color_2mass", "movimiento", "gaia")
                              for c in groups[g]]].apply(lambda x: x.notna().mean()).round(3)
    write_json(out / "cobertura_por_clase.json", cov.to_dict(orient="index"))
    return {"summary": {"rows": len(t), "columns": len(t.columns), "table": path.name,
                        "match": {k: v["matched"] for k, v in match_info.items()}}}
