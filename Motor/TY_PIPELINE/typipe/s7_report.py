"""Etapa 7: informe legible (INFORME.md) a partir de los JSON de cada etapa."""
from __future__ import annotations

import json
from pathlib import Path

from .common import read_json, utc, write_text


def _get(path: Path):
    return read_json(path) if path.is_file() else None


def fmt(x, nd=3):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def run(cfg: dict, run_dir: Path, log) -> dict:
    d = {k: run_dir / k for k in ("00_inventario", "01_variables", "02_particion", "03_eda",
                                  "04_importancia", "05_modelo", "06_spherex")}
    inv = _get(d["00_inventario"] / "inventario.json") or {}
    part = _get(d["02_particion"] / "particion_resumen.json") or {}
    eda = _get(d["03_eda"] / "B_resumen.json") or {}
    imp = _get(d["04_importancia"] / "importancia_resumen.json") or {}
    exp = _get(d["05_modelo"] / "experimentos.json") or {}
    fin = _get(d["05_modelo"] / "modelo_final.json") or {}
    sx = _get(d["06_spherex"] / "spherex_resumen.json") or {}
    tr = _get(run_dir / "07_extraccion_fits" / "trayectorias_y_movimiento_propio.json") or {}
    estado = _get(run_dir / "ESTADO.json") or {}
    L = [f"# Informe clasificador T/Y — {cfg['run_id']}", "",
         f"Generado: {utc()}. Todo lo de abajo sale de archivos de esta carpeta; nada es estimado a mano.", "",
         "## 1. Datos usados", "",
         f"- Objetos: {inv.get('n_objects')} → {inv.get('classes')}",
         f"- SPHEREx: {inv.get('spherex', {}).get('on_disk', {}).get('fits')} FITS en disco de "
         f"{inv.get('spherex', {}).get('index_rows')} del índice (5 objetivos piloto).",
         "- No disponible localmente (no se usa): Euclid, COSMOS, ZTF, datos simulados. "
         "Spitzer solo como ch1/ch2 de UltracoolSheet (existe solo para enanas → solo subanálisis T vs Y).", "",
         "## 2. Partición espacial (fijada antes de mirar la etiqueta)", "",
         f"- Celdas: {part.get('cells_total')} totales, {part.get('cells_test')} de test; solapamiento: {part.get('overlap_cells')}",
         f"- Desarrollo: {part.get('dev_counts')}", f"- Test externo: {part.get('test_counts')}", "",
         "## 3. EDA (solo desarrollo para pruebas con etiqueta)", "",
         "Variables con mayor separación entre clases (Kruskal–Wallis, ε²):", ""]
    for r in eda.get("top_kruskal_epsilon2", [])[:8]:
        L.append(f"- `{r['variable']}`: ε²={fmt(r['epsilon2'])}, q={fmt(r['q_bh'], 1) if r['q_bh'] and r['q_bh'] > 1e-3 else '<0.001'}")
    L += ["", "Faltantes más asociados a la clase (V de Cramér; alto = la ausencia delata la clase):", ""]
    for r in eda.get("faltantes_mas_asociados", [])[:6]:
        L.append(f"- `{r['variable']}`: V={fmt(r['cramers_v'])}")
    het = eda.get("zonas_heterogeneas_D>0.2", [])
    L += ["", f"Variables con distribución distinta entre zonas del cielo (KS D>0.2): {len(het)}", ""]
    L += ["## 4. Atajos: qué logra el modelo con información que NO debería usar", "",
          "| Experimento | bal_acc CV | bal_acc repesado por brillo | recall T | recall Y | precisión Y |", "|---|---|---|---|---|---|"]
    for k, v in exp.items():
        L.append(f"| {k} | {fmt(v['cv']['bal_acc'])} | {fmt(v['cv_repesado_por_brillo']['bal_acc'])} | "
                 f"{fmt(v['cv']['recall_T'])} | {fmt(v['cv']['recall_Y'])} | {fmt(v['cv'].get('precision_Y'))} |")
    L += ["", "Lectura: E0 usa solo faltantes, separaciones de cruce, posición y brillo. Si E0 es alto, "
          "la muestra permite acertar sin física; por eso esas variables quedan fuera del modelo.", "",
          "## 5. Importancia de variables (mixta)", ""]
    for k, v in imp.items():
        if not k.startswith("E"):
            continue
        L += [f"**{k}** — {v['n_variables']} variables, {v['n_clusters']} clusters, bal_acc OOF {fmt(v['bal_acc_oof'])}",
              f"- Cluster dominante: `{v['cluster_dominante']}` (cuota {fmt(v['cuota_dominante'], 2)})",
              f"- Boruta confirmadas: {', '.join(v['boruta_confirmadas']) or '—'}",
              f"- Consenso (rango medio de 5 métodos): {', '.join(v['top_consenso'])}", ""]
    if imp.get("T_vs_Y_top"):
        L += ["Subanálisis T vs Y (AUC univariado, solo enanas):", ""]
        for r in imp["T_vs_Y_top"]:
            L.append(f"- `{r['variable']}`: AUC={fmt(r['auc_simetrica'])} (n_Y={r['n_Y']})")
        L.append("")
    if fin:
        te = fin["test_externo"]
        cmp_ = fin.get("comparacion_base_vs_robusto_cv", {})
        L += ["## 6. Dependencia de una sola variable: modelo base vs robusto", "",
              "Prueba de estrés: en validación se apaga cada cluster como si esa medición faltara.", "",
              "| Variante | bal_acc limpio | peor caso al apagar un cluster | cluster más crítico |", "|---|---|---|---|"]
        for k, v in cmp_.items():
            L.append(f"| {k} | {fmt(v['limpio']['bal_acc'])} | {fmt(v['peor_caso_estres'])} | `{v['cluster_mas_critico']}` |")
        L += ["", f"Elegido: **{fin['variante']}** ({fin['regla_eleccion']}).", "",
              "## 7. Test espacial externo (evaluado una sola vez)", "",
              f"- bal_acc {fmt(te['limpio']['bal_acc'])}, macro-F1 {fmt(te['limpio']['macro_f1'])}, "
              f"AP T/Y {fmt(te['limpio']['ap_TY'])}",
              f"- Peso de clases: potencia {fin.get('potencia_peso_clases')} (elegida por CV, ver 05_modelo/eleccion_peso_clases.json)",
              f"- precisión Y {fmt(te['limpio'].get('precision_Y'))}; recall T {fmt(te['limpio']['recall_T'])} (IC95 {te['IC95_recall_T']}), "
              f"recall Y {fmt(te['limpio']['recall_Y'])} (IC95 {te['IC95_recall_Y']})",
              f"- Umbral 'desconocido' τ={fin['umbral_desconocido'].get('tau')}: cobertura "
              f"{fmt(te['con_desconocido']['cobertura'])}, precisión T/Y aceptadas "
              f"{fmt(te['con_desconocido']['precision_TY_aceptadas'])}",
              f"- Con brillo igualado: bal_acc {fmt(te['repesado_por_brillo']['bal_acc'])}", "",
              "Estrés en test (bal_acc al apagar cada cluster):", ""]
        for k, v in te["estres_por_cluster"].items():
            L.append(f"- sin `{k}`: {fmt(v['bal_acc'])}")
        L.append("")
    if sx:
        L += ["## 8. SPHEREx (5 objetivos; descriptivo)", "",
              f"- Espectros: {sx.get('espectros')}", f"- QA de FITS: { {k: v for k, v in sx.get('fits_qa', {}).items() if k != 'por_objetivo_estado'} }", ""]
    if tr:
        L += ["## 8b. Extracción completa de los FITS: trayectorias y movimiento propio", "",
              f"Método: {tr.get('metodo')}. Estado: {tr.get('estado')}.", "",
              "| Objetivo | Exposiciones | Limpias | μα* catálogo | μα* medido | μδ catálogo | μδ medido | residuo mediano |",
              "|---|---|---|---|---|---|---|---|"]
        for name, v in tr.get("objetivos", {}).items():
            pm = v.get("movimiento_propio", {})
            a, b = pm.get("pmra", {}), pm.get("pmdec", {})
            def m(x):
                return "—" if not x else f"{x['medido_mas_yr']:.0f} ± {x['err_mas_yr']:.0f}"
            L.append(f"| {name} | {v['exposiciones']} | {v['limpias_para_astrometria']} | "
                     f"{v['pm_catalogo_mas_yr'][0]:.0f} | {m(a)} | {v['pm_catalogo_mas_yr'][1]:.0f} | {m(b)} | "
                     f"{fmt(v.get('residuo_mediano_arcsec'), 2)}″ |")
        L += ["", "μ en mas/año. 'Medido' = catálogo + pendiente de los residuos. Figuras en 07_extraccion_fits/figuras/.", ""]
    warns = [w for s in estado.get("stages", {}).values() for w in s.get("warnings", [])]
    L += ["## 9. Advertencias registradas", ""] + [f"- {w}" for w in warns] + ["",
          "## 10. Límites honestos", "",
          "- Solo 50 Y en total: los intervalos de recall Y son anchos; no hay modelo final 'validado' para Y.",
          "- Las estrellas de control vienen de 40 campos Gaia: su brillo y su posición no representan el cielo.",
          "- SPHEREx cubre 5 objetos: no entra al clasificador; los índices son de control.",
          "- Paralaje del observador no corregido en las posiciones de SPHEREx (heredado del piloto).",
          "- La importancia predictiva no implica causa física."]
    write_text(run_dir / "INFORME.md", "\n".join(L) + "\n")
    return {"summary": {"informe": "INFORME.md"}}
