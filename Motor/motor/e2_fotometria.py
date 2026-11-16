"""Etapa 2 · Fotometría forzada SPHEREx por exposición, leyendo solo el recorte desde S3 — DESCARGA.

Qué hace
1. Por objeto y detector elige hasta N exposiciones del índice (`exposiciones_por_detector`), repartidas
   entre épocas (primera, última y las del medio), para no bajar las ~400 que cubren cada punto.
2. Por cada exposición lee 15×15 px de IMAGE, ZODI, VARIANCE y FLAGS desde el bucket público de S3
   (bloques de 64 KB, igual que el backend), centra el recorte en la posición propagada a MJD-AVG y mide:
   - fondo: mediana en anillo de 4–7 px (IMAGE − ZODI);
   - flujo total: ajuste lineal de una PSF gaussiana con la sigma de cada detector (la misma tabla que usa
     el backend en sus coadds, para que entrenamiento y servicio midan igual);
   - máscara: todos los bits de FLAGS definidos en la cabecera salvo SOURCE y OUTLIER (decisión del equipo
     para objetos que se mueven);
   - λ en la posición del objeto (WCS espectral 'W').
3. Guarda por lotes (parte_00001.parquet, ...). Al relanzar, salta lo medido; los errores de lectura se
   reintentan.

Salidas (salidas/2_fotometria_spherex/)
- plan.parquet            exposiciones elegidas
- partes/parte_*.parquet  una fila por medición (oid, obs_id, detector, mjd, x, y, lambda_um, flux_jy, err_jy,
                          snr, estado, ...)
- fotometria.parquet      todas las partes unidas
- resumen.json
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from .comun import out_dir, save_parquet, write_json
from .spherex_io import fotometria_forzada, jyear_from_mjd, leer_recorte, propagate


def elegir(idx: pd.DataFrame, n: int) -> pd.DataFrame:
    """Hasta n exposiciones por (oid, detector), repartidas entre épocas."""
    out = []
    for (_, _), g in idx.groupby(["oid", "detector"], sort=False):
        g = g.sort_values("t_min")
        if len(g) <= n:
            out.append(g)
            continue
        # ronda por épocas: primero una por época (empezando por extremos), luego se completa
        picks = []
        epocas = sorted(g["epoch_idx"].unique())
        orden = []
        lo, hi = 0, len(epocas) - 1
        while lo <= hi:
            orden.append(epocas[lo])
            if hi != lo:
                orden.append(epocas[hi])
            lo, hi = lo + 1, hi - 1
        grupos = {e: list(g.index[g["epoch_idx"] == e]) for e in epocas}
        while len(picks) < n and any(grupos.values()):
            for e in orden:
                if grupos[e] and len(picks) < n:
                    lst = grupos[e]
                    picks.append(lst.pop(len(lst) // 2))
        out.append(g.loc[sorted(picks)])
    return pd.concat(out, ignore_index=True) if out else idx.iloc[:0]


def run(cfg: dict, log) -> dict:
    sx = cfg["spherex"]
    src = Path(cfg["rutas"]["salidas"]) / "1_indice_spherex"
    out = out_dir(cfg, "2_fotometria_spherex")
    partes = out / "partes"
    partes.mkdir(exist_ok=True)
    idx = pd.read_parquet(src / "indice_spherex.parquet")
    sel = pd.read_parquet(src / "seleccion.parquet").set_index("oid")
    plan_path = out / "plan.parquet"
    if plan_path.is_file():
        plan = pd.read_parquet(plan_path)
    else:
        plan = elegir(idx, int(sx["exposiciones_por_detector"]))
        save_parquet(plan, plan_path)
    hechos = set()
    previas = sorted(partes.glob("parte_*.parquet"))
    for p in previas:
        d = pd.read_parquet(p, columns=["oid", "s3_key", "estado"])
        d = d[d["estado"] != "ERROR_LECTURA"]
        hechos.update(zip(d["oid"].astype(int), d["s3_key"]))
    todo = plan[[(int(o), k) not in hechos for o, k in zip(plan["oid"], plan["s3_key"])]]
    log.info("fotometría: %d lecturas pendientes de %d (concurrencia %d)", len(todo), len(plan), sx["s3_concurrencia"])

    sig = {int(k): float(v) for k, v in sx["psf_sigma_px"].items()}
    remote = bool(sx.get("_remoto", True))  # las pruebas locales lo ponen en False

    def one(r) -> dict:
        s = sel.loc[int(r.oid)]

        def pos(mjd):
            return propagate(float(s.ra_ref), float(s.dec_ref), float(s.pmra), float(s.pmdec),
                             float(s.epoca_ref), jyear_from_mjd(mjd))
        base = {"oid": int(r.oid), "obs_id": r.obs_id, "detector": int(r.detector), "s3_key": r.s3_key,
                "epoch_idx": int(r.epoch_idx), "coleccion": r.coleccion}
        last = None
        for attempt in range(int(sx["s3_reintentos"])):
            try:
                rc = leer_recorte(r.s3_url, pos, size=int(sx["recorte_px"]), remote=remote,
                                  read_lambda=bool(sx["leer_lambda"]))
                if rc is None:
                    return {**base, "estado": "FUERA_DEL_DETECTOR"}
                ph = fotometria_forzada(rc, sig.get(int(r.detector), 0.45), float(sx["radio_fotometria_px"]),
                                        tuple(sx["anillo_fondo_px"]), sx["bits_no_enmascarar"],
                                        float(sx["cobertura_psf_min"]))
                ph["detector_cabecera"] = ph.pop("detector")
                return {**base, **ph}
            except Exception as exc:  # red, S3, archivo raro
                last = repr(exc)[:300]
                time.sleep(1.5 * (attempt + 1))
        return {**base, "estado": "ERROR_LECTURA", "error": last}

    buf, n_part = [], len(previas)
    t0, done = time.monotonic(), 0
    cada = int(sx["guardar_cada"])

    def flush():
        nonlocal buf, n_part
        if buf:
            n_part += 1
            save_parquet(pd.DataFrame(buf), partes / f"parte_{n_part:05d}.parquet")
            buf = []

    with ThreadPoolExecutor(max_workers=int(sx["s3_concurrencia"])) as ex:
        futs = [ex.submit(one, r) for r in todo.itertuples(index=False)]
        for f in as_completed(futs):
            buf.append(f.result())
            done += 1
            if len(buf) >= cada:
                flush()
            if done % 500 == 0 or done == len(todo):
                rate = done / max(time.monotonic() - t0, 1e-6)
                log.info("fotometría %d/%d (%.1f lecturas/s, faltan ~%.0f min)", done, len(todo), rate,
                         (len(todo) - done) / max(rate, 1e-6) / 60)
    flush()

    allp = [pd.read_parquet(p) for p in sorted(partes.glob("parte_*.parquet"))]
    ph = pd.concat(allp, ignore_index=True) if allp else pd.DataFrame(columns=["oid", "s3_key", "estado"])
    # una medición por (oid, s3_key): la última buena gana a errores anteriores
    ph["_err"] = (ph["estado"] == "ERROR_LECTURA").astype(int)
    ph = ph.sort_values("_err").drop_duplicates(["oid", "s3_key"], keep="first").drop(columns="_err")
    save_parquet(ph, out / "fotometria.parquet")
    estados = ph["estado"].value_counts().to_dict()
    ok = ph[ph["estado"] == "OK"]
    resumen = {"lecturas_plan": int(len(plan)), "mediciones": int(len(ph)), "estados": estados,
               "objetos_con_alguna_medicion_ok": int(ok["oid"].nunique()),
               "snr_mediana_por_detector": ok.groupby("detector")["snr"].median().round(2).to_dict()
               if len(ok) else {}}
    write_json(out / "resumen.json", resumen)
    avisos = []
    n_err = estados.get("ERROR_LECTURA", 0)
    if n_err:
        avisos.append(f"{n_err} lecturas con error (relanzar la etapa las reintenta)")
    return {"resumen": resumen, "avisos": avisos}
