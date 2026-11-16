"""Utilidades comunes del motor: configuración, rutas, JSON, registro y ESTADO.json.

Reutiliza las convenciones de TY_PIPELINE (estados honestos, escritura atómica) para que
las dos partes del paquete se lean igual.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

PAQUETE = Path(__file__).resolve().parent
RAIZ = PAQUETE.parent
VERSION = "1.0.0"

ETAPAS = ["1_indice_spherex", "2_fotometria_spherex", "3_features_spherex",
          "4_preprocesamiento", "5_modelos", "6_exportar", "7_informe"]


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path, block: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def _default(o):
    try:
        import numpy as np
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o) if np.isfinite(o) else None
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:
        pass
    return str(o)


def _clean(o):
    if isinstance(o, float):
        return o if o == o and o not in (float("inf"), float("-inf")) else None
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def write_json(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    text = json.dumps(_clean(json.loads(json.dumps(value, default=_default))), ensure_ascii=False, indent=2)
    tmp.write_text(text + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save_parquet(df, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    return path


def load_config(path: Path | None = None) -> dict:
    cfg_path = Path(path) if path else RAIZ / "config" / "motor.json"
    cfg = read_json(cfg_path)
    base = cfg_path.resolve().parent
    for k, v in list(cfg["rutas"].items()):
        p = Path(os.path.expandvars(os.path.expanduser(v)))
        cfg["rutas"][k] = str(p if p.is_absolute() else (base / p).resolve())
    cfg["_config_path"] = str(cfg_path.resolve())
    cfg["_config_sha256"] = sha256(cfg_path)
    return cfg


def ty_run_dir(cfg: dict) -> Path:
    """Carpeta de TY_PIPELINE con features y partición. Si run_004 no existe aún, usa run_003."""
    main = Path(cfg["rutas"]["ty_run"])
    if (main / "02_particion" / "_HECHO.json").is_file():
        return main
    alt = Path(cfg["rutas"]["ty_run_respaldo"])
    if (alt / "02_particion" / "_HECHO.json").is_file():
        return alt
    raise FileNotFoundError(f"No hay salida de TY_PIPELINE en {main} ni en {alt}. Ejecute primero las etapas 00-02 de TY.")


def out_dir(cfg: dict, *parts: str) -> Path:
    p = Path(cfg["rutas"]["salidas"]).joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_logger(cfg: dict) -> logging.Logger:
    log = logging.getLogger("motor")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    d = out_dir(cfg)
    fh = logging.FileHandler(d / "motor.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)
    return log


def package_versions() -> dict:
    import importlib.metadata as md
    names = ("numpy", "pandas", "pyarrow", "scipy", "scikit-learn", "xgboost", "torch", "astropy",
             "fsspec", "aiohttp", "requests", "onnx", "onnxruntime", "skl2onnx", "onnxmltools")
    out = {"python": platform.python_version(), "platform": platform.platform()}
    for n in names:
        try:
            out[n] = md.version(n)
        except md.PackageNotFoundError:
            out[n] = None
    return out


class Estado:
    """salidas/ESTADO.json: qué etapa terminó, cuál falló y por qué, en pocas líneas."""

    def __init__(self, cfg: dict):
        self.path = out_dir(cfg) / "ESTADO.json"
        self.touched: set[str] = set()  # etapas de ESTE proceso: dos procesos pueden correr a la vez
        if self.path.exists():
            self.data = read_json(self.path)
        else:
            self.data = {"motor_version": VERSION, "created_utc": utc(),
                         "etapas": {s: {"estado": "PENDIENTE"} for s in ETAPAS}}
        for s in ETAPAS:
            self.data["etapas"].setdefault(s, {"estado": "PENDIENTE"})
        self.save()

    def save(self):
        # se relee el archivo y solo se actualizan las etapas de este proceso (descargas y modelos en paralelo)
        if self.path.exists():
            try:
                disk = read_json(self.path)
                for s in ETAPAS:
                    if s not in self.touched and s in disk.get("etapas", {}):
                        self.data["etapas"][s] = disk["etapas"][s]
            except (ValueError, OSError):
                pass
        et = self.data["etapas"]
        ok = [s for s in ETAPAS if et[s]["estado"] in ("OK", "OK_CON_AVISOS", "OMITIDA")]
        fail = [s for s in ETAPAS if et[s]["estado"] == "FALLO"]
        run = [s for s in ETAPAS if et[s]["estado"] == "EN_CURSO"]
        self.data["resumen"] = {"terminadas": f"{len(ok)}/{len(ETAPAS)}", "en_curso": run, "fallidas": fail,
                                "global": "FALLO" if fail else "COMPLETO" if len(ok) == len(ETAPAS)
                                else "EN_CURSO" if run else "PARCIAL"}
        self.data["updated_utc"] = utc()
        write_json(self.path, self.data)

    def start(self, s: str) -> float:
        self.touched.add(s)
        self.data["etapas"][s] = {"estado": "EN_CURSO", "inicio_utc": utc()}
        self.save()
        return time.monotonic()

    def finish(self, s: str, t0: float, resumen: dict | None = None, avisos: list | None = None):
        e = self.data["etapas"][s]
        e.update({"estado": "OK_CON_AVISOS" if avisos else "OK", "fin_utc": utc(),
                  "segundos": round(time.monotonic() - t0, 1)})
        if resumen:
            e["resumen"] = resumen
        if avisos:
            e["avisos"] = avisos[:20]
        self.save()

    def omit(self, s: str, motivo: str):
        self.touched.add(s)
        self.data["etapas"][s] = {"estado": "OMITIDA", "motivo": motivo, "fin_utc": utc()}
        self.save()

    def fail(self, s: str, t0: float, exc: BaseException):
        e = self.data["etapas"][s]
        e.update({"estado": "FALLO", "fin_utc": utc(), "segundos": round(time.monotonic() - t0, 1),
                  "error": repr(exc)[:2000], "traceback": traceback.format_exc()[-3000:]})
        self.save()


def import_typipe(cfg: dict):
    """Permite reutilizar funciones de TY_PIPELINE (lectura de catálogos con recibos, etc.)."""
    p = str(Path(cfg["rutas"]["ty_pipeline"]))
    if p not in sys.path:
        sys.path.insert(0, p)
    import typipe  # noqa: F401
    return typipe


def ty_config(cfg: dict) -> dict:
    import_typipe(cfg)
    from typipe.common import load_config as ty_load
    return ty_load(Path(cfg["rutas"]["ty_pipeline"]) / "config" / "config.json")
