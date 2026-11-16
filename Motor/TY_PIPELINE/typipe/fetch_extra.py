"""Descarga trazable de columnas que faltan para ingeniería de características:
CatWISE2020 completo (fotometría *_pm, errores de μ, paralaje WISE) y AllWISE completo (W3/W4).

Uso: python -m typipe.fetch_extra [--config config/config.json]
- Mismo servicio que funcionó antes: NOIRLab Astro Data Lab (consulta anónima).
- Posición de cada objeto propagada por movimiento propio a la época del catálogo.
- Lotes de 100 posiciones, radio 3", reanudable: un lote con recibo válido no se repite.
- Recibo JSON por lote con SQL, hash de entrada (objects) y hash de la respuesta.
- Escribe SOLO en <noirlab_catalogs>_extra/ dentro de NASA SPACE APPS (no toca la entrada original).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

from .common import load_config, sha256, utc, write_json
from .data import load_objects

SERVICE = "https://datalab.noirlab.edu/query/query"
TABLES = {"catwise_full": ("catwise2020.main", 2015.4), "allwise_full": ("allwise.source", 2010.5)}


def propagate(part, epoch_to):
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astropy.time import Time
    import warnings
    ra = np.empty(len(part))
    dec = np.empty(len(part))
    for ep in part["epoch"].unique():
        m = (part["epoch"] == ep).to_numpy()
        s = part.loc[m]
        c = SkyCoord(ra=s["ra"].to_numpy(float) * u.deg, dec=s["dec"].to_numpy(float) * u.deg,
                     pm_ra_cosdec=np.nan_to_num(s["pmra"].to_numpy(float)) * u.mas / u.yr,
                     pm_dec=np.nan_to_num(s["pmdec"].to_numpy(float)) * u.mas / u.yr,
                     obstime=Time(float(ep), format="jyear"))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mv = c.apply_space_motion(new_obstime=Time(epoch_to, format="jyear"))
        ra[m], dec[m] = mv.ra.deg, mv.dec.deg
    return ra, dec


def query(sql: str) -> bytes:
    params = {"sql": sql, "ofmt": "csv", "async": "False", "drop": "False", "out": "None", "profile": "default"}
    url = SERVICE + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"X-DL-AuthToken": "anonymous.0.0.anon_access",
                                                       "X-DL-TimeoutRequest": "60"})
            with urllib.request.urlopen(req, timeout=75) as r:
                body = r.read(8_000_001)
            if len(body) > 8_000_000 or not body.startswith(b"oid,ra_q,dec_q,"):
                raise RuntimeError("respuesta no es CSV válido: " + body[:200].decode("utf-8", "replace"))
            return body
        except (urllib.error.URLError, TimeoutError, ConnectionError, RuntimeError) as exc:
            last = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                raise
            time.sleep(min(60, 2 ** attempt))
    raise RuntimeError(f"Data Lab falló tras reintentos: {last!r}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--batch", type=int, default=100)
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    objects, osha = load_objects(cfg)
    root = Path(cfg["paths"]["extra_catalogs"])
    status = {"service": SERVICE, "started_utc": utc(), "objects_sha256": osha, "tables": {}}
    for name, (table, epoch) in TABLES.items():
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        n_batches = math.ceil(len(objects) / a.batch)
        done = new = 0
        total_bytes = 0
        for b in range(n_batches):
            part = objects.iloc[b * a.batch:(b + 1) * a.batch]
            stem = f"batch_{b:05d}"
            csv_path, rec_path = folder / f"{stem}.csv", folder / f"{stem}.json"
            if csv_path.is_file() and rec_path.is_file():
                rec = json.loads(rec_path.read_text(encoding="utf-8"))
                if rec.get("response_sha256") == sha256(csv_path) and rec.get("input_sha256") == osha:
                    done += 1
                    total_bytes += csv_path.stat().st_size
                    continue
            ra, dec = propagate(part, epoch)
            values = ",".join(f"({int(o)},{r:.10f},{d:.10f})" for o, r, d in zip(part["oid"], ra, dec))
            sql = (f"SELECT t.oid,t.ra_q,t.dec_q,c.* FROM (VALUES {values}) AS t(oid,ra_q,dec_q), {table} AS c "
                   "WHERE q3c_join(t.ra_q,t.dec_q,c.ra,c.dec,0.000833333333)")
            body = query(sql)
            tmp = csv_path.with_suffix(".csv.tmp")
            tmp.write_bytes(body)
            tmp.replace(csv_path)
            write_json(rec_path, {"source": "NOIRLab Astro Data Lab", "catalog": table, "epoch_jyear": epoch,
                                  "radius_arcsec": 3.0, "query_sql": sql, "queried_utc": utc(),
                                  "input_sha256": osha, "rows_in": len(part),
                                  "response_bytes": len(body), "response_sha256": hashlib.sha256(body).hexdigest(),
                                  "complete": True})
            done += 1
            new += 1
            total_bytes += len(body)
            if new % 25 == 0:
                print(f"{utc()} {name}: {done}/{n_batches} lotes, {total_bytes / 1e6:.1f} MB", flush=True)
                write_json(root / "descarga_estado.json", {**status, "en_curso": name,
                                                           "lotes": f"{done}/{n_batches}"})
        status["tables"][name] = {"table": table, "batches": n_batches, "done": done,
                                  "bytes": total_bytes, "status": "COMPLETE" if done == n_batches else "INCOMPLETE"}
        print(f"{utc()} {name}: COMPLETO {done}/{n_batches}, {total_bytes / 1e6:.1f} MB", flush=True)
    status["finished_utc"] = utc()
    status["all_complete"] = all(v["status"] == "COMPLETE" for v in status["tables"].values())
    write_json(root / "descarga_estado.json", status)
    return 0 if status["all_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
