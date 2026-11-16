"""Prueba sin red de las etapas 1–3 (índice, fotometría, features SPHEREx).

Reemplaza la consulta SIA por una falsa que fabrica archivos MEF sintéticos (IMAGE, FLAGS, VARIANCE, ZODI,
mismo formato que SPHEREx) con una fuente gaussiana de flujo conocido en la posición del objeto, y comprueba
que la fotometría recupera ese flujo. No toca datos reales ni salidas reales.

Uso:  python tests/prueba_spherex_sintetica.py
"""
from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from motor import comun, e1_indice, e2_fotometria, e3_features_spherex  # noqa: E402

PIX_ARCSEC = 6.15
SIGMA = {1: 0.415, 2: 0.383, 3: 0.391, 4: 0.516, 5: 0.517, 6: 0.522}
# flujo inyectado (Jy) por detector: una enana fría casi no se ve en D1–D3 y brilla en D5–D6
FLUJO = {"frio": [2e-5, 3e-5, 4e-5, 1.5e-4, 6e-4, 5e-4], "normal": [8e-4, 7e-4, 6e-4, 4e-4, 2.5e-4, 2e-4]}


def hacer_mef(path: Path, ra: float, dec: float, det: int, flux_jy: float, mjd: float, rng) -> None:
    from astropy.io import fits
    from scipy.special import erf
    n = 120
    omega = (PIX_ARCSEC / 3600 * math.pi / 180) ** 2
    amp = flux_jy / (omega * 1e6)                  # MJy/sr integrados
    xs = np.arange(n)
    s = SIGMA[det] * math.sqrt(2)
    x0 = y0 = (n - 1) / 2 + 0.3                    # fuente a 0.3 px del centro del píxel
    fx = 0.5 * (erf((xs + 0.5 - x0) / s) - erf((xs - 0.5 - x0) / s))
    psf = np.outer(fx, fx)
    sky_sigma = 0.002
    img = (0.1 + amp * psf + rng.normal(0, sky_sigma, (n, n))).astype(np.float32)
    var = np.full((n, n), sky_sigma ** 2, np.float32)
    zodi = np.full((n, n), 0.1, np.float32)
    flags = np.zeros((n, n), np.int32)
    flags[int(y0) - 1:int(y0) + 2, int(x0) - 1:int(x0) + 2] |= 1 << 21   # SOURCE: no debe enmascarar
    flags[5, 5] |= 1 << 10                                                # HOT lejos de la fuente
    h = fits.Header()
    h["CTYPE1"], h["CTYPE2"] = "RA---TAN", "DEC--TAN"
    h["CRVAL1"], h["CRVAL2"] = ra, dec
    h["CRPIX1"] = h["CRPIX2"] = x0 + 1             # FITS es 1-based
    h["CDELT1"], h["CDELT2"] = -PIX_ARCSEC / 3600, PIX_ARCSEC / 3600
    h["MJD-AVG"], h["DETECTOR"], h["BUNIT"] = mjd, det, "MJy / sr"
    fh = fits.Header()
    for bit, name in {0: "TRANSIENT", 1: "OVERFLOW", 10: "HOT", 19: "OUTLIER", 21: "SOURCE", 26: "BLOOM"}.items():
        fh[f"MSKN{bit:04d}"] = name
    prim = fits.PrimaryHDU()
    prim.header["MJD-AVG"] = mjd
    fits.HDUList([prim, fits.ImageHDU(img, h, name="IMAGE"), fits.CompImageHDU(flags, fh, name="FLAGS"),
                  fits.ImageHDU(var, h, name="VARIANCE"), fits.ImageHDU(zodi, h, name="ZODI")]).writeto(path, overwrite=True)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="prueba_spherex_"))
    files = tmp / "fits"
    files.mkdir()
    cfg_src = comun.read_json(RAIZ / "config" / "motor.json")
    cfg_src["rutas"] = {k: str((RAIZ / "config" / v).resolve()) for k, v in cfg_src["rutas"].items()}
    cfg_src["rutas"]["salidas"] = str(tmp / "salidas")
    sx = cfg_src["spherex"]
    sx.update({"seleccion_por_clase": {"star": 3, "M": 1, "L": 1, "T": 3, "Y": 2}, "s3_base": "", "_remoto": False,
               "sia_concurrencia": 2, "s3_concurrencia": 4, "leer_lambda": True, "exposiciones_por_detector": 2,
               "guardar_cada": 7, "colecciones": ["spherex_dr1", "spherex_qr3"]})  # QR3 trae el duplicado a quitar
    (tmp / "motor.json").write_text(json.dumps(cfg_src), encoding="utf-8")
    cfg = comun.load_config(tmp / "motor.json")
    log = comun.get_logger(cfg)
    rng = np.random.default_rng(1)
    clase_de = {}

    def sia_falso(url, ra, dec, radius, collection, **kw):
        """3 épocas × 6 detectores × 2 exposiciones; QR3 repite una exposición de DR1 (duplicado a quitar)."""
        key = f"{ra:.5f}_{dec:.5f}"
        tipo = clase_de.get(key, "normal")
        rows = []
        for ep, tmin in enumerate((60800.0, 60985.0, 61170.0)):
            for det in range(1, 7):
                for k in range(2):
                    if collection == "spherex_qr3" and not (ep == 0 and det == 1 and k == 0):
                        continue
                    name = f"{key}_e{ep}_d{det}_{k}.fits"
                    p = files / name
                    if not p.exists():
                        hacer_mef(p, ra, dec, det, FLUJO[tipo][det - 1], 61000.0, rng)
                    rows.append({"access_url": str(p), "cloud_access": json.dumps({"aws": {"key": str(p)}}),
                                 "t_min": tmin + k * 0.01, "t_max": tmin + k * 0.01 + 0.001,
                                 "obs_id": f"OBS_{ep}_{k}", "energy_bandpassname": f"SPHEREx-D{det}"})
        return rows

    # posición que consultará e1 (propagada a mjd_referencia_indice) → tipo de fuente a inyectar
    pos = e1_indice.posiciones(cfg, log)
    sel = e1_indice.seleccionar(cfg, pos, log)
    from motor.spherex_io import jyear_from_mjd, propagate
    yr = jyear_from_mjd(float(sx["mjd_referencia_indice"]))
    for r in sel.itertuples():
        ra, dec = propagate(r.ra_ref, r.dec_ref, r.pmra, r.pmdec, float(r.epoca_ref), yr)
        clase_de[f"{ra:.5f}_{dec:.5f}"] = "frio" if r.label in ("T", "Y") else "normal"
    comun.save_parquet(sel, comun.out_dir(cfg, "1_indice_spherex") / "seleccion.parquet")
    e1_indice.sia_query = sia_falso

    r1 = e1_indice.run(cfg, log)
    r2 = e2_fotometria.run(cfg, log)
    r3 = e3_features_spherex.run(cfg, log)
    ph = __import__("pandas").read_parquet(Path(cfg["rutas"]["salidas"]) / "2_fotometria_spherex" / "fotometria.parquet")
    ok = ph[ph["estado"] == "OK"].copy()
    # flujo esperado por fila
    sel_i = sel.set_index("oid")
    ok["esperado"] = [FLUJO["frio" if str(sel_i.loc[o, "label"]) in ("T", "Y") else "normal"][d - 1]
                      for o, d in zip(ok["oid"], ok["detector"])]
    ratio = (ok["flux_jy"] / ok["esperado"])
    brillantes = ok["esperado"] >= 1e-4
    checks = {
        "indice_sin_duplicados": r1["resumen"]["duplicados_entre_colecciones"] > 0
        and not __import__("pandas").read_parquet(Path(cfg["rutas"]["salidas"]) / "1_indice_spherex" / "indice_spherex.parquet")
        .duplicated(["oid", "obs_id", "detector"]).any(),
        "tres_epocas": r1["resumen"]["epocas_por_objeto_mediana"] == 3,
        "todas_ok": r2["resumen"]["estados"].get("OK", 0) == len(ph),
        "flujo_recuperado_mediana": float(ratio[brillantes].median()),
        "flujo_dentro_5pct": bool((ratio[brillantes] - 1).abs().median() < 0.05),
        "color_frio_c65": float(__import__("pandas").read_parquet(Path(cfg["rutas"]["salidas"]) / "3_features_spherex" / "features_spherex.parquet")
                                .query("label in ['T','Y']")["spx_c54"].median()),
    }
    print(json.dumps({"e1": r1["resumen"], "e2": r2["resumen"], "e3": r3["resumen"], "checks": checks},
                     indent=1, ensure_ascii=False, default=str)[:6000])
    good = checks["indice_sin_duplicados"] and checks["tres_epocas"] and checks["todas_ok"] and checks["flujo_dentro_5pct"]
    print("RESULTADO:", "OK" if good else "FALLA", "| carpeta temporal:", tmp)
    if good:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
