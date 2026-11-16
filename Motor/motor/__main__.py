"""Punto de entrada: python -m motor [--config ruta] [--etapas ...] [--sin-spherex]

Etapas (en orden): 1_indice_spherex 2_fotometria_spherex 3_features_spherex 4_preprocesamiento 5_modelos
6_exportar 7_informe. Las 1 y 2 descargan (necesitan red) y se pueden relanzar: siguen donde quedaron.
Las 4–7 se repiten completas en segundos/minutos. El avance queda en salidas/ESTADO.json.
"""
from __future__ import annotations

import argparse
import sys

from .comun import ETAPAS, Estado, get_logger, load_config, package_versions, write_json, out_dir


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Motor clasificatorio: SPHEREx + preprocesamiento + modelos + ONNX")
    ap.add_argument("--config", default=None)
    ap.add_argument("--etapas", nargs="*", default=ETAPAS, choices=ETAPAS)
    ap.add_argument("--sin-spherex", action="store_true", help="omite 1-3 (modelo solo con catálogo)")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    log = get_logger(cfg)
    est = Estado(cfg)
    write_json(out_dir(cfg) / "entorno.json", {"versiones": package_versions(), "config": cfg})
    etapas = [e for e in ETAPAS if e in a.etapas]
    if a.sin_spherex:  # no se marcan como omitidas: otro proceso puede estar descargando en paralelo
        etapas = [e for e in etapas if e not in ETAPAS[:3]]
    for e in etapas:
        t0 = est.start(e)
        log.info("=== %s ===", e)
        try:
            res = correr(e, cfg, log) or {}
            est.finish(e, t0, res.get("resumen"), res.get("avisos"))
        except Exception as exc:
            log.exception("%s falló", e)
            est.fail(e, t0, exc)
            log.error("Se detiene la secuencia: revisar salidas/ESTADO.json (error y traceback)")
            return 1
    log.info("FIN: %s", est.data["resumen"])
    return 0


def correr(e: str, cfg: dict, log):
    if e == "1_indice_spherex":
        from . import e1_indice as m
    elif e == "2_fotometria_spherex":
        from . import e2_fotometria as m
    elif e == "3_features_spherex":
        from . import e3_features_spherex as m
    elif e == "4_preprocesamiento":
        from . import e4_preprocesamiento as m
    elif e == "5_modelos":
        from . import e5_modelos as m
    elif e == "6_exportar":
        from . import e6_exportar as m
    else:
        from . import e7_informe as m
    return m.run(cfg, log)


if __name__ == "__main__":
    sys.exit(main())
