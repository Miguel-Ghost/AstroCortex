"""Utilidades comunes: rutas, JSON atómico, hashes, registro y ESTADO.json."""
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

PACKAGE_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = PACKAGE_DIR.parent
VERSION = "1.0.0"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path, block: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _default(o):
    try:
        import numpy as np
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return None if not np.isfinite(o) else float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:
        pass
    if isinstance(o, Path):
        return str(o)
    return str(o)


def _clean(o):
    """Convierte NaN/inf en None para que el JSON sea estándar."""
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
    text = json.dumps(_clean(json.loads(json.dumps(value, default=_default))),
                      ensure_ascii=False, indent=2)
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


def load_config(path: Path | None) -> dict:
    cfg_path = Path(path) if path else PIPELINE_DIR / "config" / "config.json"
    cfg = read_json(cfg_path)
    cfg["_config_path"] = str(cfg_path.resolve())
    cfg["_config_sha256"] = sha256(cfg_path)
    base = cfg_path.resolve().parent

    def resolve(p: str) -> str:
        q = Path(os.path.expandvars(os.path.expanduser(p)))
        return str(q if q.is_absolute() else (base / q).resolve())

    for key, value in list(cfg["paths"].items()):
        cfg["paths"][key] = resolve(value)
    return cfg


def get_logger(out_dir: Path) -> logging.Logger:
    log = logging.getLogger("typipe")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    out_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(out_dir / "pipeline.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)
    return log


def package_versions() -> dict:
    import importlib.metadata as md
    names = ("numpy", "pandas", "pyarrow", "scipy", "scikit-learn", "matplotlib", "astropy")
    out = {"python": platform.python_version(), "platform": platform.platform()}
    for n in names:
        try:
            out[n] = md.version(n)
        except md.PackageNotFoundError:
            out[n] = None
    return out


class Estado:
    """ESTADO.json: resumen breve y legible del avance para supervisión barata."""

    def __init__(self, out_dir: Path, stages: list[str]):
        self.path = Path(out_dir) / "ESTADO.json"
        if self.path.exists():
            self.data = read_json(self.path)
        else:
            self.data = {"pipeline_version": VERSION, "created_utc": utc(),
                         "stages": {s: {"status": "PENDING"} for s in stages}}
        for s in stages:
            self.data["stages"].setdefault(s, {"status": "PENDING"})
        self.data["stage_order"] = stages
        self.save()

    def save(self):
        self.data["updated_utc"] = utc()
        order = self.data["stage_order"]
        st = self.data["stages"]
        done = [s for s in order if st[s]["status"] in ("OK", "OK_WITH_WARNINGS", "SKIPPED_UP_TO_DATE")]
        failed = [s for s in order if st[s]["status"] == "FAILED"]
        running = [s for s in order if st[s]["status"] == "RUNNING"]
        self.data["resumen"] = {
            "completadas": f"{len(done)}/{len(order)}",
            "en_curso": running,
            "fallidas": failed,
            "global": ("FALLÓ" if failed else "COMPLETO" if len(done) == len(order)
                       else "EN_CURSO" if running else "PARCIAL"),
        }
        write_json(self.path, self.data)

    def start(self, stage: str):
        self.data["stages"][stage] = {"status": "RUNNING", "started_utc": utc()}
        self.save()
        return time.monotonic()

    def finish(self, stage: str, t0: float, summary: dict | None = None, warnings: list | None = None):
        entry = self.data["stages"][stage]
        entry.update({"status": "OK_WITH_WARNINGS" if warnings else "OK",
                      "finished_utc": utc(), "seconds": round(time.monotonic() - t0, 1)})
        if summary:
            entry["summary"] = summary
        if warnings:
            entry["warnings"] = warnings[:20]
        self.save()

    def fail(self, stage: str, t0: float, exc: BaseException):
        entry = self.data["stages"][stage]
        entry.update({"status": "FAILED", "finished_utc": utc(),
                      "seconds": round(time.monotonic() - t0, 1),
                      "error": repr(exc)[:2000],
                      "traceback_tail": traceback.format_exc()[-3000:]})
        self.save()

    def skip(self, stage: str, reason: str):
        self.data["stages"][stage].update({"status": "SKIPPED_UP_TO_DATE", "reason": reason,
                                           "checked_utc": utc()})
        self.save()
