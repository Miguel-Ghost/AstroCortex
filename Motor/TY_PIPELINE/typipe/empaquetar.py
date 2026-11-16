"""Empaqueta TODO lo necesario para entrenar en otra computadora (sin los FITS de 125 GB).

Uso: python -m typipe.empaquetar [--config config/config.json] [--destino RUTA] [--con-resultados run_003 ...]
Crea <destino>/PAQUETE_TY/ y PAQUETE_TY.zip con:
  TY_PIPELINE/            código, tests, docs, lanzadores; config/config.json con rutas RELATIVAS
  datos_entrada/          processed/*.parquet, UltracoolSheet, catalogos_noirlab (con recibos), índice SPHEREx
  datos_extra_TY/         descarga complementaria (con recibos)
  resultados_TY/<run>/    resultados elegidos (opcional)
  MANIFIESTO.json         ruta, tamaño y SHA-256 de cada archivo
  LEEME_TRASPASO.md       pasos en la otra máquina
Los FITS no se copian: solo sirven a las etapas 06/07 (SPHEREx), no al entrenamiento.
"""
from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

from .common import PIPELINE_DIR, load_config, sha256, utc, write_json, write_text

EXCLUDE_DIRS = {".venv", "__pycache__", "logs", ".git"}


def copy_tree(src: Path, dst: Path, skip_dirs=EXCLUDE_DIRS, skip_suffix=(".pyc", ".tmp")) -> int:
    n = 0
    for p in src.rglob("*"):
        rel = p.relative_to(src)
        if any(part in skip_dirs for part in rel.parts) or p.suffix in skip_suffix or p.is_dir():
            continue
        q = dst / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, q)
        n += 1
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--destino", type=Path, default=None)
    ap.add_argument("--con-resultados", nargs="*", default=None)
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    P = cfg["paths"]
    dest_root = a.destino or Path(P["output_root"]).parent
    pkg = Path(dest_root) / "PAQUETE_TY"
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)
    log = {}
    log["TY_PIPELINE"] = copy_tree(PIPELINE_DIR, pkg / "TY_PIPELINE")
    din = pkg / "datos_entrada"
    log["processed"] = copy_tree(Path(P["processed"]), din / "processed")
    ucs = Path(P["ultracoolsheet"])
    (din / "ultracoolsheet").mkdir(parents=True)
    for f in ucs.parent.glob("*.csv"):
        shutil.copy2(f, din / "ultracoolsheet" / f.name)
    log["catalogos_noirlab"] = copy_tree(Path(P["noirlab_catalogs"]), din / "catalogos_noirlab")
    idx = Path(P["spherex_index"])
    if idx.is_file():
        (din / "spherex_index").mkdir(parents=True)
        shutil.copy2(idx, din / "spherex_index" / idx.name)
    st = Path(P["fits_status"])
    if st.is_file():
        (din / "logs").mkdir(parents=True)
        shutil.copy2(st, din / "logs" / st.name)
    extra = Path(P.get("extra_catalogs", ""))
    if extra.is_dir():
        log["datos_extra_TY"] = copy_tree(extra, pkg / "datos_extra_TY")
    runs = a.con_resultados if a.con_resultados is not None else [cfg["run_id"]]
    for r in runs:
        src = Path(P["output_root"]) / r
        if src.is_dir():
            log[f"resultados_TY/{r}"] = copy_tree(src, pkg / "resultados_TY" / r,
                                                  skip_suffix=(".pyc", ".tmp", ".lock"))

    # Config portátil: rutas relativas a TY_PIPELINE/config
    raw_cfg = json.loads((PIPELINE_DIR / "config" / "config.json").read_text(encoding="utf-8"))
    raw_cfg["paths"] = {
        "input_root": "../../datos_entrada",
        "processed": "../../datos_entrada/processed",
        "ultracoolsheet": f"../../datos_entrada/ultracoolsheet/{ucs.name}",
        "noirlab_catalogs": "../../datos_entrada/catalogos_noirlab",
        "spherex_index": "../../datos_entrada/spherex_index/" + idx.name,
        "spherex_raw": "../../datos_entrada/spherex_raw_mef",
        "fits_status": "../../datos_entrada/logs/" + st.name,
        "extra_catalogs": "../../datos_extra_TY",
        "output_root": "../../resultados_TY",
    }
    raw_cfg["_nota"] = ("Config portátil generada por typipe.empaquetar. Para usar los FITS, copie "
                        "spherex_raw_mef dentro de datos_entrada/ o cambie 'spherex_raw'.")
    write_json(pkg / "TY_PIPELINE" / "config" / "config.json", raw_cfg)

    manifest = []
    for p in sorted(pkg.rglob("*")):
        if p.is_file():
            manifest.append({"ruta": p.relative_to(pkg).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p)})
    total = sum(m["bytes"] for m in manifest)
    write_json(pkg / "MANIFIESTO.json", {"generado_utc": utc(), "archivos": len(manifest), "bytes": total,
                                         "conteo_por_bloque": log, "run_id": cfg["run_id"], "lista": manifest})
    write_text(pkg / "LEEME_TRASPASO.md", f"""# Traspaso del clasificador T/Y a otra computadora

Generado: {utc()} · {len(manifest)} archivos · {total / 1e6:.1f} MB (sin FITS).

## En la otra computadora (Windows)
1. Descomprimir `PAQUETE_TY.zip` en cualquier carpeta (ruta corta, p. ej. `C:\\TY`).
2. Instalar Python 3.13 (python.org) si no está.
3. Doble clic en `TY_PIPELINE\\windows\\01_instalar_entorno.bat` (crea .venv e instala dependencias).
4. Doble clic en `TY_PIPELINE\\windows\\04_prueba_sintetica.bat` (comprueba que todo funciona; ~10 min).
5. Doble clic en `TY_PIPELINE\\windows\\02_ejecutar_pipeline.bat` (entrena; ~35 min).
   Avance en `resultados_TY\\{cfg['run_id']}\\ESTADO.json`; informe en `INFORME.md`.

## Verificar integridad
`MANIFIESTO.json` tiene el SHA-256 de cada archivo. Los recibos de cada lote de catálogo
están junto a su CSV y el pipeline los verifica solo antes de usarlos.

## Qué NO viene
Los 1927 FITS SPHEREx (125 GB): no hacen falta para entrenar. Solo las etapas 06 y 07 los usan;
sin ellos esas etapas quedan marcadas como no ejecutadas y el resto funciona.
""")
    zpath = pkg.with_suffix(".zip")
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(pkg.rglob("*")):
            if p.is_file():
                z.write(p, Path("PAQUETE_TY") / p.relative_to(pkg))
    print(f"Paquete: {pkg} ({len(manifest)} archivos, {total / 1e6:.1f} MB) | zip: {zpath} "
          f"({zpath.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
