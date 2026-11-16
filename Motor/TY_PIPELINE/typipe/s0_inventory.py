"""Etapa 0: inventario de entradas existentes, hashes y estado de los FITS."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .common import read_json, sha256, write_json, utc, package_versions
from .data import input_files, load_objects


def count_fits(raw: Path) -> dict:
    n_fits = n_receipts = n_part = 0
    total = 0
    for dirpath, _, files in os.walk(raw):
        for name in files:
            if name.endswith(".fits"):
                n_fits += 1
                total += os.path.getsize(os.path.join(dirpath, name))
            elif name.endswith(".fits.json"):
                n_receipts += 1
            elif name.endswith(".part"):
                n_part += 1
    return {"fits": n_fits, "receipts": n_receipts, "partial": n_part, "bytes": total}


def run(cfg: dict, out: Path, log) -> dict:
    paths = cfg["paths"]
    files = []
    for f in input_files(cfg):
        files.append({"path": str(f), "bytes": f.stat().st_size, "sha256": sha256(f)})
    objects, objects_sha = load_objects(cfg)
    classes = objects["label"].value_counts().to_dict()

    catalogs = {}
    for name in cfg["catalogs"]:
        folder = Path(paths["noirlab_catalogs"]) / name
        catalogs[name] = {"csv": len(list(folder.glob("chunk_*.csv"))),
                          "receipts": len(list(folder.glob("chunk_*.json")))}

    raw = Path(paths["spherex_raw"])
    fits = count_fits(raw) if raw.is_dir() else {"fits": 0}
    status_file = Path(paths["fits_status"])
    status_text = status_file.read_text(encoding="utf-8", errors="replace") if status_file.is_file() else ""
    dl = raw / "download_status.json"
    download_status = read_json(dl) if dl.is_file() else None
    n_index = 0
    idx = Path(paths["spherex_index"])
    if idx.is_file():
        with idx.open(encoding="utf-8") as fh:
            n_index = sum(1 for line in fh if line.strip())

    warnings = []
    if fits.get("fits", 0) != n_index:
        warnings.append(f"FITS en disco {fits.get('fits')} != índice {n_index}")
    if "FIN FITS completos OK" not in status_text:
        warnings.append("run_2.status no confirma fin de la descarga FITS")

    inv = {"generated_utc": utc(), "objects_sha256": objects_sha, "n_objects": len(objects),
           "classes": classes, "input_files": files, "noirlab_catalogs": catalogs,
           "spherex": {"index_rows": n_index, "on_disk": fits, "download_status": download_status,
                       "bat_status_tail": status_text[-300:]},
           "packages": package_versions(), "config_sha256": cfg["_config_sha256"],
           "scope": {
               "usado": ["UltracoolSheet (etiquetas)", "Gaia DR3 (controles y cruce por id)",
                         "CatWISE2020/AllWISE/2MASS/unWISE (NOIRLab, recibos verificados)",
                         "SPHEREx DR1/QR3: 1927 MEF de 5 objetivos piloto + fotometría forzada"],
               "no_disponible_localmente": ["Euclid", "COSMOS", "Spitzer (salvo ch1/ch2 de UltracoolSheet)",
                                            "ZTF", "Datos simulados Roman/Rubin"],
               "solo_metodo": ["IRSA Techniques & Tools", "CatNorth (arXiv:2310.12704) §3"]}}
    write_json(out / "inventario.json", inv)
    log.info("inventario: %d objetos %s; FITS %s/%s", len(objects), classes, fits.get("fits"), n_index)
    return {"summary": {"n_objects": len(objects), "classes": classes,
                        "fits_on_disk": fits.get("fits"), "fits_index": n_index},
            "warnings": warnings, "objects_sha256": objects_sha}
