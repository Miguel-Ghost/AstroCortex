"""Etapa 1 · Índice SPHEREx por objeto (IRSA SIA) — DESCARGA, necesita red.

Qué hace
1. Elige los objetos a medir: por clase, según `spherex.seleccion_por_clase` (estratificado, semilla fija),
   más los 5 objetivos piloto del reto como control (no entran al entrenamiento).
2. Posición de cada objeto con una fuente IGUAL para todas las clases: CatWISE2020 (posición en MJD 57170
   + movimiento propio CatWISE) cuando el objeto tiene contraparte; si no, la de objects.parquet.
   La procedencia queda en `pos_fuente` (auditoría, nunca predictor).
3. Una consulta SIA por objeto y colección, con reintentos y concurrencia baja (IRSA pide moderación).
   Cada objeto se guarda en caché al terminar: si la etapa se corta, al relanzarla sigue donde quedó.
4. Consolida: quita duplicados de exposición (misma obs_id + detector en dos colecciones, se prefiere DR1),
   descarta claves `qr2/`, arma la URL de S3 y numera las épocas (hueco > 20 días = época nueva).

Salidas (salidas/1_indice_spherex/)
- seleccion.parquet          oid, label, role, pos_fuente, ra_ref, dec_ref, pmra, pmdec, epoca_ref (jyear)
- cache/<oid>.parquet        respuesta SIA cruda por objeto (reanudación)
- indice_spherex.parquet     oid, coleccion, obs_id, detector, t_min, t_max, s3_key, s3_url, epoch_idx
- resumen.json
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from .comun import out_dir, read_json, save_parquet, ty_config, ty_run_dir, write_json
from .spherex_io import detector_number, jyear_from_mjd, key_from_url, propagate, s3_key, sia_query


def posiciones(cfg: dict, log) -> pd.DataFrame:
    """Posición de referencia por oid: CatWISE si existe, si no objects.parquet."""
    tcfg = ty_config(cfg)  # también deja importable el paquete typipe
    from typipe.data import best_match, load_catalog, load_objects
    objects, objects_sha = load_objects(tcfg)
    sx = cfg["spherex"]
    pos = objects[["oid", "label", "ra", "dec", "pmra", "pmdec", "epoch"]].copy()
    pos["pos_fuente"] = "objects"
    pos = pos.rename(columns={"ra": "ra_ref", "dec": "dec_ref", "epoch": "epoca_ref"})
    try:
        cw, _ = load_catalog(tcfg, "catwise", objects_sha)
        best = best_match(cw, float(tcfg["match_radius_arcsec"]))[["oid", "ra", "dec", "pmra", "pmdec"]]
        best = best.dropna(subset=["ra", "dec"]).set_index("oid")
        m = pos["oid"].isin(best.index)
        b = best.loc[pos.loc[m, "oid"]]
        pos.loc[m, "ra_ref"] = b["ra"].to_numpy(float)
        pos.loc[m, "dec_ref"] = b["dec"].to_numpy(float)
        # CatWISE da μ en arcsec/año
        pos.loc[m, "pmra"] = pd.to_numeric(b["pmra"], errors="coerce").to_numpy(float) * 1000.0
        pos.loc[m, "pmdec"] = pd.to_numeric(b["pmdec"], errors="coerce").to_numpy(float) * 1000.0
        pos.loc[m, "epoca_ref"] = jyear_from_mjd(float(sx["mjd_catwise"]))
        pos.loc[m, "pos_fuente"] = "catwise"
        log.info("posiciones: %d por CatWISE, %d por objects", int(m.sum()), int((~m).sum()))
    except Exception as exc:  # sin CatWISE: todo por objects (queda anotado)
        log.warning("CatWISE no disponible para posiciones (%r); se usa objects.parquet", exc)
    return pos


def seleccionar(cfg: dict, pos: pd.DataFrame, log) -> pd.DataFrame:
    sx = cfg["spherex"]
    rng = np.random.default_rng(int(cfg["semilla"]))
    part = pd.read_parquet(ty_run_dir(cfg) / "02_particion" / "particion.parquet")[["oid", "role"]]
    pos = pos.merge(part, on="oid", how="left")
    chosen = []
    for label, n in sx["seleccion_por_clase"].items():
        sub = pos[pos["label"] == label]
        if n is None or int(n) < 0 or int(n) >= len(sub):
            chosen.append(sub)
        else:
            chosen.append(sub.iloc[np.sort(rng.choice(len(sub), int(n), replace=False))])
    sel = pd.concat(chosen, ignore_index=True)
    sel["control"] = False
    if sx.get("incluir_pilotos", True):
        f = Path(cfg["rutas"]["datos_entrada"]) / "processed" / "spherex_sample_targets.parquet"
        if f.is_file():
            pil = pd.read_parquet(f)
            pil = pd.DataFrame({"oid": pil["oid"].astype("int64"), "label": "control:" + pil["target"].astype(str),
                                "ra_ref": pil["ra"], "dec_ref": pil["dec"], "pmra": pil["pmra"],
                                "pmdec": pil["pmdec"], "epoca_ref": pil["epoch"], "pos_fuente": "piloto",
                                "role": "control", "control": True})
            sel = pd.concat([sel, pil], ignore_index=True)
    log.info("selección SPHEREx: %s", sel["label"].value_counts().to_dict())
    return sel


def run(cfg: dict, log) -> dict:
    sx = cfg["spherex"]
    out = out_dir(cfg, "1_indice_spherex")
    cache = out / "cache"
    cache.mkdir(exist_ok=True)
    sel_path = out / "seleccion.parquet"
    if sel_path.is_file():  # la selección se fija la primera vez (reanudar no la cambia)
        sel = pd.read_parquet(sel_path)
        log.info("selección existente: %d objetos", len(sel))
    else:
        sel = seleccionar(cfg, posiciones(cfg, log), log)
        save_parquet(sel, sel_path)

    mjd_ref = float(sx["mjd_referencia_indice"])
    year_ref = jyear_from_mjd(mjd_ref)
    todo = [r for r in sel.itertuples(index=False) if not (cache / f"{int(r.oid)}.parquet").is_file()]
    log.info("SIA: %d objetos pendientes de %d (concurrencia %d)", len(todo), len(sel), sx["sia_concurrencia"])

    import requests
    local = threading.local()

    def session():
        if not hasattr(local, "s"):
            local.s = requests.Session()
        return local.s

    def one(r) -> tuple[int, int, str | None]:
        ra, dec = propagate(r.ra_ref, r.dec_ref, r.pmra, r.pmdec, float(r.epoca_ref), year_ref)
        rows = []
        for col in sx["colecciones"]:
            for row in sia_query(sx["sia_url"], ra, dec, float(sx["sia_radio_grados"]), col,
                                 timeout=float(sx["sia_timeout_s"]), tries=int(sx["sia_reintentos"]),
                                 session=session()):
                row["coleccion"] = col
                rows.append(row)
        df = pd.DataFrame(rows, columns=list(rows[0].keys()) if rows else
                          ["access_url", "cloud_access", "t_min", "t_max", "obs_id", "energy_bandpassname", "coleccion"])
        df.insert(0, "oid", int(r.oid))
        save_parquet(df.astype({c: "string" for c in ("access_url", "cloud_access", "obs_id",
                                                       "energy_bandpassname", "coleccion")}), cache / f"{int(r.oid)}.parquet")
        return int(r.oid), len(df), None

    errores = {}
    t0, done = time.monotonic(), 0
    with ThreadPoolExecutor(max_workers=int(sx["sia_concurrencia"])) as ex:
        futs = {ex.submit(one, r): int(r.oid) for r in todo}
        for f in as_completed(futs):
            oid = futs[f]
            try:
                f.result()
            except Exception as exc:
                errores[str(oid)] = repr(exc)[:300]
            done += 1
            if done % 50 == 0 or done == len(todo):
                rate = done / max(time.monotonic() - t0, 1e-6)
                log.info("SIA %d/%d (%.2f obj/s, faltan ~%.0f min, errores %d)", done, len(todo), rate,
                         (len(todo) - done) / max(rate, 1e-6) / 60, len(errores))
    write_json(out / "errores_sia.json", errores)

    # ---- consolidación ----
    parts = [pd.read_parquet(p) for p in sorted(cache.glob("*.parquet"))]
    raw = pd.concat([p for p in parts if len(p)], ignore_index=True) if parts else pd.DataFrame()
    resumen = {"objetos_seleccionados": int(len(sel)), "objetos_con_cache": len(parts),
               "objetos_con_error": len(errores), "filas_sia": int(len(raw))}
    if raw.empty:
        save_parquet(pd.DataFrame(columns=["oid", "coleccion", "obs_id", "detector", "t_min", "t_max",
                                           "s3_key", "s3_url", "epoch_idx"]), out / "indice_spherex.parquet")
        write_json(out / "resumen.json", resumen)
        return {"resumen": resumen, "avisos": ["SIA no devolvió exposiciones"]}
    raw["s3_key"] = raw["cloud_access"].map(s3_key)
    raw["s3_key"] = raw["s3_key"].fillna(raw["access_url"].map(key_from_url))
    raw["detector"] = raw["energy_bandpassname"].map(detector_number)
    raw["t_min"] = pd.to_numeric(raw["t_min"], errors="coerce")
    raw["t_max"] = pd.to_numeric(raw["t_max"], errors="coerce")
    n0 = len(raw)
    sin_clave = int(raw["s3_key"].isna().sum())
    raw = raw.dropna(subset=["s3_key", "detector", "t_min"])
    qr2 = raw["s3_key"].str.startswith("qr2/")
    raw = raw[~qr2]
    prio = {c: i for i, c in enumerate(sx["prioridad_coleccion"])}
    raw["_p"] = raw["coleccion"].map(prio).fillna(99)
    raw = raw.sort_values(["oid", "obs_id", "detector", "_p"])
    dup = raw.duplicated(["oid", "obs_id", "detector"], keep="first")
    raw = raw[~dup].drop(columns="_p")
    raw["detector"] = raw["detector"].astype(int)
    raw["s3_url"] = sx["s3_base"] + raw["s3_key"]
    raw = raw.sort_values(["oid", "t_min"]).reset_index(drop=True)
    gap = raw.groupby("oid")["t_min"].diff().fillna(0) > float(sx["hueco_epoca_dias"])
    raw["epoch_idx"] = gap.astype(int).groupby(raw["oid"]).cumsum()
    idx = raw[["oid", "coleccion", "obs_id", "detector", "t_min", "t_max", "s3_key", "s3_url", "epoch_idx"]]
    save_parquet(idx, out / "indice_spherex.parquet")
    por_obj = idx.groupby("oid").agg(n=("obs_id", "size"), epocas=("epoch_idx", "nunique"))
    resumen.update({"filas_sin_clave_s3": sin_clave, "filas_qr2_descartadas": int(qr2.sum()),
                    "duplicados_entre_colecciones": int(dup.sum()), "filas_indice": int(len(idx)),
                    "objetos_con_exposiciones": int(idx["oid"].nunique()),
                    "exposiciones_por_objeto_mediana": float(por_obj["n"].median()),
                    "epocas_por_objeto_mediana": float(por_obj["epocas"].median()),
                    "por_detector": idx["detector"].value_counts().sort_index().to_dict(),
                    "filas_crudas": n0})
    write_json(out / "resumen.json", resumen)
    avisos = [f"{len(errores)} objetos sin respuesta de SIA (se reintentan al relanzar la etapa)"] if errores else []
    return {"resumen": resumen, "avisos": avisos}
