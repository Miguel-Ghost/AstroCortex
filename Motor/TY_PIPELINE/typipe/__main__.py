"""Punto de entrada: python -m typipe [--config ruta] [--stages ...] [--force]

Etapas reanudables: si una etapa ya terminó con las mismas entradas, configuración
y versión de código, se salta. El progreso queda en <salida>/<run_id>/ESTADO.json.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .common import Estado, VERSION, get_logger, load_config, read_json, sha256, write_json, utc

STAGES = ["00_inventario", "01_variables", "02_particion", "03_eda", "04_importancia",
          "05_modelo", "06_spherex", "07_extraccion_fits", "08_informe"]
DEPENDS = {"01_variables": ["00_inventario"], "02_particion": ["01_variables"],
           "03_eda": ["02_particion"], "04_importancia": ["02_particion"],
           "05_modelo": ["04_importancia"], "06_spherex": ["00_inventario"],
           "07_extraccion_fits": ["00_inventario"], "08_informe": []}
# Huella de código POR ETAPA: cambiar una etapa no obliga a repetir las demás.
STAGE_MODULES = {"00_inventario": ["s0_inventory"], "01_variables": ["s1_features"],
                 "02_particion": ["s2_split"], "03_eda": ["s3_eda"],
                 "04_importancia": ["s4_importance", "ml"], "05_modelo": ["s5_model", "ml"],
                 "06_spherex": ["s6_spherex"], "07_extraccion_fits": ["s8_fits_extraction"],
                 "08_informe": ["s7_report"]}
SHARED = ["common", "data"]


def code_fingerprint(stage: str) -> str:
    pkg = Path(__file__).resolve().parent
    import hashlib
    h = hashlib.sha256()
    for name in SHARED + STAGE_MODULES[stage]:
        f = pkg / f"{name}.py"
        h.update(f.name.encode() + sha256(f).encode())
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pipeline clasificador T/Y (datos existentes)")
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--stages", nargs="*", default=STAGES, choices=STAGES)
    ap.add_argument("--force", action="store_true", help="repetir etapas aunque estén al día")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    root = Path(cfg["paths"]["output_root"])
    inp = Path(cfg["paths"]["input_root"]).resolve()
    if root.resolve() == inp or inp in root.resolve().parents:
        raise SystemExit("La salida no puede estar dentro de la carpeta de entrada (solo lectura)")
    run_dir = root / cfg["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    log = get_logger(run_dir)
    estado = Estado(run_dir, STAGES)
    write_json(run_dir / "config_usada.json", cfg)
    log.info("typipe %s | salida %s", VERSION, run_dir)

    objects_sha = None
    for stage in STAGES:
        if stage not in a.stages:
            continue
        sdir = run_dir / stage
        sdir.mkdir(parents=True, exist_ok=True)
        marker = sdir / "_HECHO.json"
        if objects_sha is None and stage != "00_inventario":
            inv = run_dir / "00_inventario" / "inventario.json"
            objects_sha = read_json(inv)["objects_sha256"] if inv.is_file() else None
        upstream = {d: (read_json(run_dir / d / "_HECHO.json").get("finished_utc")
                        if (run_dir / d / "_HECHO.json").is_file() else None)
                    for d in DEPENDS.get(stage, [])}
        fp = {"code": code_fingerprint(stage), "config": cfg["_config_sha256"], "objects": objects_sha, "upstream": upstream}
        if marker.is_file() and not a.force and stage != "00_inventario":
            prev = read_json(marker)
            if prev.get("fingerprint") == fp:
                estado.skip(stage, "mismas entradas, config y código")
                log.info("%s: al día, se salta", stage)
                continue
        missing = [d for d, v in upstream.items() if v is None]
        if missing:
            estado.data["stages"][stage] = {"status": "BLOCKED", "falta": missing, "checked_utc": utc()}
            estado.save()
            log.error("%s bloqueada: faltan %s", stage, missing)
            continue
        t0 = estado.start(stage)
        log.info("=== %s ===", stage)
        try:
            res = run_stage(stage, cfg, run_dir, sdir, log) or {}
            if stage == "00_inventario":
                objects_sha = res.get("objects_sha256")
                fp["objects"] = objects_sha
            estado.finish(stage, t0, res.get("summary"), res.get("warnings"))
            write_json(marker, {"finished_utc": utc(), "fingerprint": fp})
        except Exception as exc:
            log.exception("%s falló", stage)
            estado.fail(stage, t0, exc)
            if marker.is_file():
                marker.unlink()
    if "08_informe" in a.stages:
        from . import s7_report
        s7_report.run(cfg, run_dir, log)
    final = estado.data["resumen"]
    log.info("FIN: %s", final)
    return 0 if final["global"] == "COMPLETO" else 1


def run_stage(stage: str, cfg: dict, run_dir: Path, sdir: Path, log):
    d = lambda name: run_dir / name  # noqa: E731
    if stage == "00_inventario":
        from . import s0_inventory
        return s0_inventory.run(cfg, sdir, log)
    if stage == "01_variables":
        from . import s1_features
        return s1_features.run(cfg, sdir, log)
    if stage == "02_particion":
        from . import s2_split
        return s2_split.run(cfg, sdir, d("01_variables"), log)
    if stage == "03_eda":
        from . import s3_eda
        return s3_eda.run(cfg, sdir, d("01_variables"), d("02_particion"), log)
    if stage == "04_importancia":
        from . import s4_importance
        return s4_importance.run(cfg, sdir, d("01_variables"), d("02_particion"), log)
    if stage == "05_modelo":
        from . import s5_model
        return s5_model.run(cfg, sdir, d("01_variables"), d("02_particion"), d("04_importancia"), log)
    if stage == "06_spherex":
        from . import s6_spherex
        return s6_spherex.run(cfg, sdir, log)
    if stage == "07_extraccion_fits":
        from . import s8_fits_extraction
        return s8_fits_extraction.run(cfg, sdir, log)
    if stage == "08_informe":
        from . import s7_report
        return s7_report.run(cfg, run_dir, log)
    raise ValueError(stage)


if __name__ == "__main__":
    sys.exit(main())
