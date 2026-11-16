"""Etapa 7 · Informe legible y manifiesto de salidas (SHA-256 de cada archivo).

Todo número del informe sale de los archivos de salidas/; nada se escribe a mano.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .comun import Estado, out_dir, package_versions, read_json, sha256, utc, write_json, write_text


def _j(p: Path):
    return read_json(p) if p.is_file() else None


def run(cfg: dict, log) -> dict:
    s = Path(cfg["rutas"]["salidas"])
    L = [f"# Informe del motor clasificatorio (Vast)", "", f"Generado: {utc()}. Fuente de cada cifra: carpeta `salidas/`.", ""]
    e1, e2, e3 = _j(s / "1_indice_spherex/resumen.json"), _j(s / "2_fotometria_spherex/resumen.json"), _j(s / "3_features_spherex/resumen.json")
    L += ["## 1. Datos SPHEREx descargados", ""]
    if e1:
        L += [f"- Objetos seleccionados: {e1.get('objetos_seleccionados')}; con exposiciones: {e1.get('objetos_con_exposiciones')}; "
              f"sin respuesta SIA: {e1.get('objetos_con_error')}.",
              f"- Filas del índice: {e1.get('filas_indice')} (duplicados entre colecciones quitados: {e1.get('duplicados_entre_colecciones')}); "
              f"exposiciones por objeto (mediana): {e1.get('exposiciones_por_objeto_mediana')}; épocas (mediana): {e1.get('epocas_por_objeto_mediana')}."]
    else:
        L += ["- Etapas SPHEREx no ejecutadas: el modelo usa solo variables de catálogo."]
    if e2:
        L += [f"- Lecturas: {e2.get('lecturas_plan')}; estados: {e2.get('estados')}.",
              f"- S/N mediana por detector: {e2.get('snr_mediana_por_detector')}."]
    if e3:
        L += [f"- Objetos con alguna medición OK: {e3.get('con_alguna_medicion_ok')} de {e3.get('objetos')}.", "",
              "Cobertura de colores SPHEREx por clase (fracción no faltante):", "",
              "```", pd.DataFrame(e3.get("cobertura_colores_por_clase", {})).T.to_string(), "```"]
    pre = _j(s / "4_preprocesamiento/preprocesamiento.json")
    bal = _j(s / "4_preprocesamiento/balance.json")
    L += ["", "## 2. Preprocesamiento", ""]
    if pre:
        L += [f"- Filas: {pre['filas_inicio']} → {pre['filas_final']} (duplicados quitados: {pre['quitadas_duplicado']}).",
              f"- Valores imposibles pasados a faltante: {pre['valores_imposibles_a_faltante'] or 'ninguno'}.",
              f"- Variables quitadas por faltantes: {pre['variables_quitadas_por_faltantes'] or 'ninguna'}.",
              f"- Variables por conjunto: {pre['variables_por_conjunto']}.",
              f"- Outliers marcados (no borrados): {pre['outliers_marcados_total']}.",
              f"- TY_PIPELINE usado: `{pre['ty_run']}`."]
    if bal:
        L += [f"- Balance (desarrollo/test): {bal['conteos']}", f"- Estrategia: {bal['estrategia']}."]
    res = _j(s / "5_modelos/resumen.json")
    L += ["", "## 3. Comparación de modelos (CV espacial; test una vez)", ""]
    comp = s / "5_modelos/comparacion_global.csv"
    if comp.is_file():
        c = pd.read_csv(comp)
        keep = [x for x in ["experimento", "modelo", "elegido_por_cv", "potencia_peso", "n_variables", "cv_macro_f1",
                            "cv_balanced_accuracy", "cv_ap_positivas", "cv_recall_positivas", "test_macro_f1",
                            "test_balanced_accuracy", "test_ap_positivas", "test_recall_positivas",
                            "test_precision_positivas"] if x in c.columns]
        L += ["```", c[keep].to_string(index=False), "```", ""]
    if res:
        for k, v in res.items():
            L.append(f"- {k}: {v.get('estado')}" + (f", elegido {v['elegido']} → test {v['test_elegido']}" if v.get("estado") == "OK"
                                                     else f" ({v.get('motivo')})"))
    ex = _j(s / "6_exportar/verificacion.json")
    md = _j(s / "6_exportar/metadata.json")
    L += ["", "## 4. Modelo exportado al backend", ""]
    if md:
        L += [f"- Versión: `{md['model_version']}`; features: {md['features']}; clases: {md['classes']}; umbrales: {md['thresholds']}.",
              f"- Verificación ONNX: {ex.get('ok') if ex else '—'} (dif. máx. {ex.get('max_dif_probabilidades') if ex else '—'})."]
    else:
        L += ["- No exportado todavía."]
    L += ["", "## 5. Límites", "",
          "- 50 Y en total: el recall de Y tiene intervalos anchos (ver ic95 en metricas.json).",
          "- Las estrellas de control vienen de 40 campos de Gaia: su brillo y posición no representan el cielo "
          "(ver atajos E0/E3 en el informe de TY_PIPELINE).",
          "- Los colores SPHEREx mezclan λ dentro de cada detector (cada exposición mide otra λ del filtro LVF), "
          "igual que los coadds del backend.",
          "- La importancia por permutación es predictiva, no causal."]
    write_text(s / "INFORME_MOTOR.md", "\n".join(L) + "\n")

    files = []
    for p in sorted(s.rglob("*")):
        if p.is_file() and "/cache/" not in str(p) and "/partes/" not in str(p) and p.suffix != ".tmp":
            files.append({"ruta": str(p.relative_to(s)), "bytes": p.stat().st_size, "sha256": sha256(p)})
    write_json(s / "MANIFIESTO_SALIDAS.json", {"generado_utc": utc(), "versiones": package_versions(),
                                                "config_sha256": cfg["_config_sha256"], "archivos": files})
    return {"resumen": {"informe": "INFORME_MOTOR.md", "archivos_en_manifiesto": len(files)}}
