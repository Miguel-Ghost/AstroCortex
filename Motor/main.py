"""AstroCortex model repository CLI.

    python main.py ty                    TY_PIPELINE 00-04: catalog cross-match, spatial split, EDA, importance
    python main.py descargar             motor 1-3: SPHEREx index (IRSA SIA), forced photometry (S3), SPHEREx features
    python main.py entrenar              motor 4-7: preprocessing, RF vs XGBoost vs MLP, ONNX export, report
    python main.py promover              copy the last export to artifacts/models/<version>/ and artifacts/models/actual/
    python main.py publicar [--backend ../Backend]
                                         copy artifacts/models/actual (model.onnx + metadata.json) to Backend/models/,
                                         the model /api/sources serves
    python main.py predecir ENTRADA SALIDA [--modelo artifacts/models/actual]
                                         batch prediction (CSV/Parquet with the model features), same rule as the backend
    python main.py verificar [--modelo artifacts/models/actual]
                                         check the ONNX + metadata.json contract that the backend loads
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLASES_BACKEND = {"star", "galaxy", "asteroid_comet", "cold_brown_dwarf", "unknown"}
PROHIBIDAS = {"known_label", "simbad_type", "catalog_type", "catalog_status", "known_source"}


def run(cmd: list[str], cwd: Path = ROOT) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=cwd)


def cmd_ty(_a) -> int:
    return run([sys.executable, "-m", "typipe", "--config", "config/config.json", "--stages",
                "00_inventario", "01_variables", "02_particion", "03_eda", "04_importancia"], cwd=ROOT / "TY_PIPELINE")


def cmd_descargar(_a) -> int:
    return run([sys.executable, "-m", "motor", "--etapas", "1_indice_spherex", "2_fotometria_spherex",
                "3_features_spherex"])


def cmd_entrenar(_a) -> int:
    return run([sys.executable, "-m", "motor", "--etapas", "4_preprocesamiento", "5_modelos", "6_exportar",
                "7_informe"])


def cmd_promover(a) -> int:
    src = ROOT / "salidas" / "6_exportar"
    meta = json.loads((src / "metadata.json").read_text(encoding="utf-8"))
    version = meta["model_version"]
    dst = ROOT / "artifacts" / "models" / version
    dst.mkdir(parents=True, exist_ok=True)
    for f in ("model.onnx", "metadata.json", "verificacion.json", "PARA_BACKEND.md"):
        shutil.copy2(src / f, dst / f)
    actual = ROOT / "artifacts" / "models" / "actual"
    if actual.exists():
        shutil.rmtree(actual)
    shutil.copytree(dst, actual)
    rep = ROOT / "reports"
    (rep / "metrics").mkdir(parents=True, exist_ok=True)
    sal = ROOT / "salidas"
    for f in ("INFORME_MOTOR.md", "MANIFIESTO_SALIDAS.json"):
        if (sal / f).is_file():
            shutil.copy2(sal / f, rep / f)
    for f in ("comparacion_global.csv", "resumen.json"):
        if (sal / "5_modelos" / f).is_file():
            shutil.copy2(sal / "5_modelos" / f, rep / "metrics" / f)
    for e in sorted(p for p in (sal / "5_modelos").iterdir() if p.is_dir()):
        d = rep / "experiments" / e.name
        d.mkdir(parents=True, exist_ok=True)
        for f in e.iterdir():
            if f.suffix in (".json", ".csv", ".png"):
                shutil.copy2(f, d / f.name)
    print(f"promovido {version} -> artifacts/models/actual")
    return 0


def cmd_publicar(a) -> int:
    """El backend sirve Backend/models/model.onnx: esta copia es lo que llega a producción."""
    src = ROOT / "artifacts" / "models" / "actual"
    dst = Path(a.backend).resolve() / "models"
    if cmd_verificar(type("A", (), {"modelo": str(src)})()) != 0:
        print("el modelo promovido no cumple el contrato: no se publica")
        return 1
    dst.mkdir(parents=True, exist_ok=True)
    for f in ("model.onnx", "metadata.json"):
        shutil.copy2(src / f, dst / f)
    meta = json.loads((dst / "metadata.json").read_text(encoding="utf-8"))
    print(f"publicado {meta['model_version']} -> {dst}")
    return 0


def _cargar(modelo: Path):
    import onnxruntime as ort
    meta = json.loads((modelo / "metadata.json").read_text(encoding="utf-8"))
    sess = ort.InferenceSession(str(modelo / "model.onnx"), providers=["CPUExecutionProvider"])
    return meta, sess


def _probabilidades(meta, sess, rows):
    """Misma regla que OnnxPredictor del backend: relleno con fill_values, (x - mean)/scale, última salida."""
    import math

    import numpy as np
    n = len(meta["features"])
    sc = meta.get("scaler") or {}
    mean = np.asarray(sc.get("mean", [0.0] * n), np.float32)
    scale = np.asarray(sc.get("scale", [1.0] * n), np.float32)
    X = []
    for ev in rows:
        row = []
        for name in meta["features"]:
            v = ev.get(name)
            if isinstance(v, bool):
                v = float(v)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                v = meta["fill_values"].get(name, 0.0)
            row.append(float(v))
        X.append(row)
    X = (np.asarray(X, np.float32) - mean) / scale
    return np.asarray(sess.run(None, {sess.get_inputs()[0].name: X})[-1], float)


def cmd_predecir(a) -> int:
    import pandas as pd
    meta, sess = _cargar(Path(a.modelo))
    src = Path(a.entrada)
    df = pd.read_parquet(src) if src.suffix == ".parquet" else pd.read_csv(src)
    rows = df.to_dict("records")
    p = _probabilidades(meta, sess, rows)
    out = df.copy()
    for j, c in enumerate(meta["classes"]):
        out[f"p_{c}"] = p[:, j]
    best = p.argmax(1)
    labels = []
    for i, b in enumerate(best):
        c = meta["classes"][b]
        labels.append(c if p[i, b] >= meta.get("thresholds", {}).get(c, 0.0) else "unknown")
    out["label"] = labels
    out["model_version"] = meta["model_version"]
    dst = Path(a.salida)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(dst, index=False) if dst.suffix == ".parquet" else out.to_csv(dst, index=False)
    print(f"{len(out)} filas -> {dst} | {pd.Series(labels).value_counts().to_dict()}")
    return 0


def cmd_verificar(a) -> int:
    import numpy as np
    modelo = Path(a.modelo)
    meta, sess = _cargar(modelo)
    errores = []
    for k in ("model_version", "features", "classes", "fill_values"):
        if k not in meta:
            errores.append(f"falta {k} en metadata.json")
    if not set(meta.get("classes", [])) <= CLASES_BACKEND:
        errores.append(f"clases fuera del vocabulario del backend: {meta.get('classes')}")
    if PROHIBIDAS & set(meta.get("features", [])):
        errores.append(f"features prohibidas (BR-CLS-02): {PROHIBIDAS & set(meta['features'])}")
    falt = [f for f in meta.get("features", []) if f not in meta.get("fill_values", {})]
    if falt:
        errores.append(f"features sin fill_value: {falt}")
    p = _probabilidades(meta, sess, [{}, {f: v for f, v in meta["fill_values"].items()}])
    if p.shape != (2, len(meta["classes"])):
        errores.append(f"forma de salida {p.shape}, se esperaba (2, {len(meta['classes'])})")
    if not np.allclose(p.sum(1), 1.0, atol=1e-4):
        errores.append(f"las probabilidades no suman 1: {p.sum(1)}")
    print(json.dumps({"modelo": meta.get("model_version"), "features": meta.get("features"),
                      "classes": meta.get("classes"), "thresholds": meta.get("thresholds"),
                      "errores": errores}, indent=1, ensure_ascii=False))
    return 1 if errores else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("ty", "descargar", "entrenar", "promover"):
        sub.add_parser(name)
    p = sub.add_parser("predecir")
    p.add_argument("entrada")
    p.add_argument("salida")
    p.add_argument("--modelo", default=str(ROOT / "artifacts" / "models" / "actual"))
    v = sub.add_parser("verificar")
    v.add_argument("--modelo", default=str(ROOT / "artifacts" / "models" / "actual"))
    b = sub.add_parser("publicar")
    b.add_argument("--backend", default=str(ROOT.parent / "Backend"))
    a = ap.parse_args(argv)
    return {"ty": cmd_ty, "descargar": cmd_descargar, "entrenar": cmd_entrenar, "promover": cmd_promover,
            "predecir": cmd_predecir, "verificar": cmd_verificar, "publicar": cmd_publicar}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
