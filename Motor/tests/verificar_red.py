"""Comprueba desde la máquina Vast que IRSA (SIA) y el bucket S3 de SPHEREx responden, y mide la latencia.
Una consulta SIA (WISE 0855) y una lectura parcial de un archivo. No guarda nada."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor.spherex_io import clave_s3, leer_recorte, sia_query  # noqa: E402

SIA = "https://irsa.ipac.caltech.edu/SIA"
S3 = "https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/"


def main() -> int:
    ra, dec = 133.7587, -7.2416  # WISE 0855 en 2025-26
    t0 = time.time()
    try:
        rows = sia_query(SIA, ra, dec, 0.0003, "spherex_dr1", timeout=60, tries=3)
    except Exception as exc:
        print("IRSA SIA: FALLA", repr(exc)[:300])
        return 1
    print(f"IRSA SIA: OK, {len(rows)} exposiciones DR1 en {time.time() - t0:.1f} s")
    key = next((clave_s3(r) for r in rows if clave_s3(r)), None)
    print("ejemplo cloud_access:", str(rows[0].get("cloud_access"))[:120] if rows else None)
    if not key:
        print("S3: sin clave en la respuesta SIA")
        return 1
    t0 = time.time()
    try:
        rc = leer_recorte(S3 + key, lambda mjd: (ra, dec), size=15, remote=True, read_lambda=True)
    except Exception as exc:
        print("S3: FALLA", repr(exc)[:300])
        return 1
    if rc is None:
        print(f"S3: OK pero el objeto cae fuera de ese detector ({time.time() - t0:.1f} s)")
    else:
        print(f"S3: OK, recorte {rc.image.shape} D{rc.detector} λ={rc.wavelength_um} µm en {time.time() - t0:.1f} s")
    print("Estimación: con 32 hilos, unas 20-40 lecturas/s si cada lectura tarda 1-1.5 s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
