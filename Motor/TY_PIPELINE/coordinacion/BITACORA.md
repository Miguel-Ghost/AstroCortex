# Bitácora de ejecución y auditoría

| Fecha (Lima) | Agente | Evento |
|---|---|---|
| 2026-11-15 00:24 | Claude | Pipeline 1.0.0 probado de punta a punta con datos sintéticos (8/8 etapas, pandas 3.0.5, scikit-learn 1.9.1). |
| 2026-11-15 00:37 | Claude | Ejecución real run_001 lanzada (00_TODO_AUTOMATICO.bat). 00–03 OK: 11 850 objetos, 1927/1927 FITS, test espacial 58/286 celdas (10 Y, 183 T). |
| 2026-11-15 00:44 | Claude | Hallazgo propio H-01: el agrupamiento por correlación con enlace simple encadenó 10 de 15 variables en un solo cluster (cuota 75–96 %), lo que vacía la prueba de estrés. Corregido a enlace promedio (ml.py). Con la matriz real da 4 grupos con sentido físico: color medio-IR (W1−W2, J/H/Ks−W2), colores 2MASS (J−H, J−Ks, J−W1), H−Ks, movimiento (μ, H_rpm). Se re-ejecuta todo al terminar el proceso en curso. |
| 2026-11-15 00:44 | Claude | Codex y Claude Code CLI no instalados / sin tokens: la auditoría externa queda PENDIENTE. Por ahora trabaja solo Claude. |
| 2026-11-15 01:00 | Claude | Hallazgo H-02 (de la CV de run_001, precisión T/Y 0.57): el peso 'balanced' completo hace sobre-predecir Y (en test: 81 predichas Y, 4 correctas). Cambio: potencia del peso de clase elegida por CV entre {1, 0.5, 0.25} con máxima macro-F1. El test de run_001 ya fue visto: el de run_002 se informa como "segunda mirada" del mismo test. |
| 2026-11-15 01:20 | Claude | Nueva etapa 07_extraccion_fits: usa los 1927 MEF completos (recorte por exposición, IMAGE−ZODI, máscara de cabecera, gaussiana 2D, paralaje anual + μ) para trayectorias, movimiento propio medido y espectros. Huella de código por etapa. Lanzadores con log propio por ejecución (el log compartido bloqueó el arranque de run_002). |
| 2026-11-15 01:39 | Claude | run_002 relanzado como copia única (dos copias simultáneas cerradas por Paolo; añadido candado por PID). |
| 2026-11-15 02:12 | Claude | run_002 COMPLETO 9/9. Test: T/Y precisión 0.96, recall T 0.83, Y 0/10 (todas → T). Robusto: peor caso CV 0.52→0.63. Extracción: ε Indi B μ coincide con catálogo al ~2 %; WISE 0855 no fiable (S/N 2.9); Barnard/R Dra saturadas. Ver resultados_TY/run_002/LECTURA_VERIFICADA.md. |
| 2026-11-15 02:15 | Claude | H-03: subanálisis T vs Y mostraba AUC con n_Y=1–2; ahora exige ≥10 por clase (aplica desde la próxima ejecución). |
| 2026-11-15 02:30 | Claude | Paolo prioriza ingeniería de características. Falta data: CatWISE completo (w1/w2mpro_pm, σμ, par_pm) y AllWISE W3/W4. Autorizado ("sigue procesándolo"). Descarga typipe.fetch_extra (NOIRLab, ~30 MB, lotes de 100, recibos SHA) a CLASIFICADOR_TY/datos_extra_TY. Nuevos grupos: color_w3 (W2−W3, W1−W3), wise_pm (W1−W2_pm, μ/σμ, H_W2_pm), paralaje_wise (grupo aparte, E1c). E1b = conjunto anterior para comparar. Se ejecuta como run_003. |
