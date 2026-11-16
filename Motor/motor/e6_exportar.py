"""Etapa 6 · Exportar el modelo elegido del experimento servible a ONNX + metadata.json (contrato del backend).

Contrato (Backend/app/services/classifier.py, OnnxPredictor):
- model.onnx: entrada float32 [1, n_features]; la ÚLTIMA salida son las probabilidades [1, n_clases].
- metadata.json: model_version, features, classes, calibrated, thresholds, fill_values, scaler (opcional).
- El backend reemplaza cada faltante por fill_values[feature] y aplica (x − mean)/scale. Aquí el escalado y el
  recorte de la red van dentro del ONNX, así que no se envía `scaler` (identidad).
- Las clases deben ser del vocabulario del backend (star, galaxy, asteroid_comet, cold_brown_dwarf, unknown).
- Ninguna feature puede ser un tipo de catálogo (BR-CLS-02).

Verificación: onnxruntime vs el modelo original en el test, y una simulación de OnnxPredictor con diccionarios
de evidencia (valores faltantes incluidos).

Salidas (salidas/6_exportar/): model.onnx, metadata.json, verificacion.json, PARA_BACKEND.md
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import modelos as M
from .comun import out_dir, read_json, utc, write_json, write_text

CLASES_BACKEND = {"star", "galaxy", "asteroid_comet", "cold_brown_dwarf", "unknown"}
PROHIBIDAS = {"known_label", "simbad_type", "catalog_type", "catalog_status", "known_source"}

DEFINICIONES = {
    "cw_W1_W2": "CatWISE2020 w1mpro − w2mpro [mag Vega]; NaN si cc_flags/ab_flags de W1 o W2 ≠ '0'",
    "cw_mu": "hypot(pmra, pmdec) de CatWISE2020 [arcsec/año] (pmra/pmdec de CatWISE vienen en arcsec/año)",
    "cw_log_mu": "log10(max(cw_mu, 0.005)) [log arcsec/año]",
    "Hrpm_W2": "w2mpro + 5·log10(max(cw_mu, 0.005)) + 5 [mag]; movimiento propio reducido",
    "spx_c21": "−2.5·log10(F_D2/F_D1), flujos SPHEREx con ajuste de PSF gaussiana; solo si S/N ≥ 3 en ambos",
    "spx_c32": "−2.5·log10(F_D3/F_D2), misma regla",
    "spx_c43": "−2.5·log10(F_D4/F_D3), misma regla",
    "spx_c54": "−2.5·log10(F_D5/F_D4), misma regla",
    "spx_c65": "−2.5·log10(F_D6/F_D5), misma regla",
    "spx_c64": "−2.5·log10(F_D6/F_D4), misma regla",
    "spx_ch4": "log10(F_D5/F_D4) = log10(methane_index del backend); con D5 S/N≥3 y D4 S/N<3: log10(F_D5/(3·σ_D4))",
}


def a_onnx(tipo: str, model, n: int, path: Path):
    if tipo == "rf":
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType
        onx = convert_sklearn(model, initial_types=[("input", FloatTensorType([None, n]))],
                              options={id(model): {"zipmap": False}}, target_opset=17)
        path.write_bytes(onx.SerializeToString())
    elif tipo == "xgb":
        import onnxmltools
        from onnxmltools.convert.common.data_types import FloatTensorType
        onx = onnxmltools.convert_xgboost(model, initial_types=[("input", FloatTensorType([None, n]))], target_opset=15)
        path.write_bytes(onx.SerializeToString())
    else:
        import torch

        class ConSoftmax(torch.nn.Module):
            def __init__(self, net):
                super().__init__()
                self.net = net

            def forward(self, x):
                return torch.softmax(self.net(x), dim=1)

        wrapped = ConSoftmax(model).eval()
        kw = dict(input_names=["input"], output_names=["probabilities"],
                  dynamic_axes={"input": {0: "n"}, "probabilities": {0: "n"}}, opset_version=17)
        try:
            torch.onnx.export(wrapped, torch.zeros(1, n), str(path), dynamo=False, **kw)
        except TypeError:  # versiones sin el argumento dynamo
            torch.onnx.export(wrapped, torch.zeros(1, n), str(path), **kw)


def cargar(path: Path):
    if path.suffix == ".pt":
        import torch
        b = torch.load(path, map_location="cpu", weights_only=False)
        n = b["n_in"]
        net = M.construir_red(n, b["n_out"], b["capas"], float(b["dropout"]),
                              np.zeros(n), np.zeros(n), np.zeros(n), np.ones(n))
        net.load_state_dict(b["state_dict"])
        net.eval()
        return net, b["meta"]
    import joblib
    b = joblib.load(path)
    return b["modelo"], b["meta"]


class SimuladorBackend:
    """Copia mínima de OnnxPredictor._vector/predict para comprobar el contrato sin el repo del backend."""

    def __init__(self, onnx_path: Path, meta: dict):
        import onnxruntime as ort
        self.meta = meta
        self.sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name
        sc = meta.get("scaler") or {}
        n = len(meta["features"])
        self.mean = np.asarray(sc.get("mean", [0.0] * n), np.float32)
        self.scale = np.asarray(sc.get("scale", [1.0] * n), np.float32)

    def predict(self, evidence: dict) -> dict:
        row = []
        for name in self.meta["features"]:
            v = evidence.get(name)
            if isinstance(v, bool):
                v = float(v)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                v = self.meta["fill_values"].get(name, 0.0)
            row.append(float(v))
        x = ((np.asarray(row, np.float32) - self.mean) / self.scale).reshape(1, -1)
        probs = np.asarray(self.sess.run(None, {self.inp: x})[-1], float).ravel()
        cp = dict(zip(self.meta["classes"], probs, strict=True))
        best = max(cp, key=cp.get)
        label = best if cp[best] >= self.meta["thresholds"].get(best, 0.0) else "unknown"
        return {"label": label, "class_probs": cp}


def run(cfg: dict, log) -> dict:
    import onnxruntime as ort
    exp = cfg["exportar"]["experimento"]
    src = Path(cfg["rutas"]["salidas"]) / "5_modelos" / exp
    met = read_json(src / "metricas.json")
    tipo = met["elegido"]
    model, meta_m = cargar(src / met["modelos"][tipo]["archivo"])
    cols, clases, med = meta_m["columnas"], meta_m["clases"], np.asarray(meta_m["medianas"], float)
    if not set(clases) <= CLASES_BACKEND:
        raise RuntimeError(f"clases fuera del vocabulario del backend: {clases}")
    if PROHIBIDAS & set(cols):
        raise RuntimeError(f"features prohibidas por BR-CLS-02: {PROHIBIDAS & set(cols)}")
    out = out_dir(cfg, "6_exportar")
    onnx_path = out / "model.onnx"
    a_onnx(tipo, model, len(cols), onnx_path)

    tau = met["modelos"][tipo].get("umbral_clase_fria", {}).get("tau")
    fria = cfg["exportar"]["clase_fria"]
    version = f"motor-{tipo}-{exp}-{'spherex' if met['poblacion'] == 'spherex' else 'catalogo'}-{utc()[:16].replace(':', '')}"
    metadata = {
        "model_version": version,
        "features": cols,
        "classes": clases,
        "calibrated": False,
        "thresholds": {fria: tau} if tau is not None else {},
        "fill_values": {c: float(v) for c, v in zip(cols, med)},
        "feature_definitions": {c: DEFINICIONES.get(c, "ver 4_preprocesamiento/variables.json") for c in cols},
        "training": {"experimento": exp, "modelo": tipo, "potencia_peso_clase": meta_m.get("potencia_peso"),
                     "poblacion": met["poblacion"], "n_dev": met["n_dev"], "n_test": met["n_test"],
                     "cv": M.resumen_corto(met["modelos"][tipo]["cv"], clases),
                     "test": M.resumen_corto(met["modelos"][tipo]["test"], clases),
                     "particion": "espacial de TY_PIPELINE (celdas de cielo; test = 20 % de celdas)",
                     "etiquetas": "star = estrella, M o L; cold_brown_dwarf = T o Y (UltracoolSheet)"},
        "created_utc": utc(),
    }
    write_json(out / "metadata.json", metadata)

    # ---- verificación numérica ----
    tabla = pd.read_parquet(Path(cfg["rutas"]["salidas"]) / "4_preprocesamiento" / "tabla_modelo.parquet")
    t = tabla[tabla["role"] == "test"]
    if met["poblacion"] == "spherex":
        t = t[t["in_spherex"]]
    X = t[cols].to_numpy(np.float64)
    Xi = M.imputar(X, med).astype(np.float32)
    native = M.proba_mlp(model, Xi) if tipo == "mlp" else M.proba_sklearn(model, Xi, len(clases))
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    outs = sess.run(None, {sess.get_inputs()[0].name: Xi})
    onx = np.asarray(outs[-1], float)
    diff = float(np.max(np.abs(onx - native))) if len(Xi) else 0.0
    agree = float((onx.argmax(1) == native.argmax(1)).mean()) if len(Xi) else 1.0
    sim = SimuladorBackend(onnx_path, json.loads((out / "metadata.json").read_text(encoding="utf-8")))
    ejemplos = []
    for _, r in t.head(25).iterrows():
        ev = {c: (None if pd.isna(r[c]) else float(r[c])) for c in cols}
        p = sim.predict(ev)
        ejemplos.append({"oid": int(r["oid"]), "label_real": r["label"], **p})
    vacio = sim.predict({})  # todo faltante: debe responder sin error
    verif = {"onnx_salidas": [o.name for o in sess.get_outputs()], "max_dif_probabilidades": diff,
             "acuerdo_clase": agree, "n_test": int(len(Xi)), "evidencia_vacia": vacio,
             "ejemplos": ejemplos[:10], "ok": bool(diff < 1e-4 and agree > 0.999)}
    write_json(out / "verificacion.json", verif)

    md = [f"# Modelo para el backend ({version})", "",
          f"- Archivo: `model.onnx` + `metadata.json` (copiar ambos a la ruta que lee `load_predictor`).",
          f"- Modelo: {tipo} del experimento {exp}; clases {clases}; umbral {fria} = {tau}.",
          f"- Verificación ONNX vs original en test: diferencia máxima {diff:.2e}, acuerdo de clase {agree:.3f}.",
          "", "## Evidencia que el backend debe calcular por fuente (mismos nombres)", "",
          "| feature | definición |", "|---|---|"]
    md += [f"| `{c}` | {metadata['feature_definitions'][c]} |" for c in cols]
    md += ["", "Si una feature no existe para una fuente, el backend usa `fill_values` (mediana de entrenamiento).",
           f"Con todas las features faltantes este modelo responde {vacio['label']} "
           f"({', '.join(f'{k} {v:.2f}' for k, v in vacio['class_probs'].items())}): el backend debe marcar como "
           "`insufficient_data` las fuentes sin `cw_W1_W2` (la variable que más pesa) en vez de usar la predicción.",
           "Las reglas de `jpl_match` (asteroide) y `extended` (galaxia) no las aprende este modelo: conviene "
           "aplicarlas antes del modelo, como hace `RulePredictor`."]
    write_text(out / "PARA_BACKEND.md", "\n".join(md) + "\n")
    import shutil
    vdir = out / "versiones" / version.replace(":", "-")
    vdir.mkdir(parents=True, exist_ok=True)
    for f in ("model.onnx", "metadata.json", "verificacion.json", "PARA_BACKEND.md"):
        shutil.copy2(out / f, vdir / f)
    avisos = [] if verif["ok"] else [f"verificación ONNX no superada: dif {diff:.2e}, acuerdo {agree:.3f}"]
    return {"resumen": {"modelo": tipo, "experimento": exp, "version": version, "features": cols,
                        "umbral": tau, "verificacion_ok": verif["ok"]}, "avisos": avisos}
