# Informe clasificador T/Y — run_003

Generado: 2026-11-15T08:21:49+00:00. Todo lo de abajo sale de archivos de esta carpeta; nada es estimado a mano.

## 1. Datos usados

- Objetos: 11850 → {'star': 8000, 'L': 1958, 'M': 924, 'T': 918, 'Y': 50}
- SPHEREx: 1927 FITS en disco de 1927 del índice (5 objetivos piloto).
- No disponible localmente (no se usa): Euclid, COSMOS, ZTF, datos simulados. Spitzer solo como ch1/ch2 de UltracoolSheet (existe solo para enanas → solo subanálisis T vs Y).

## 2. Partición espacial (fijada antes de mirar la etiqueta)

- Celdas: 286 totales, 58 de test; solapamiento: 0
- Desarrollo: {'star': 6395, 'L': 1564, 'M': 740, 'T': 735, 'Y': 40}
- Test externo: {'star': 1605, 'L': 394, 'M': 184, 'T': 183, 'Y': 10}

## 3. EDA (solo desarrollo para pruebas con etiqueta)

Variables con mayor separación entre clases (Kruskal–Wallis, ε²):

- `aw_W1_W2`: ε²=0.665, q=<0.001
- `cw_W1_W2`: ε²=0.656, q=<0.001
- `cw_W1_W2_pm`: ε²=0.655, q=<0.001
- `gaia_M_W2`: ε²=0.621, q=<0.001
- `has_gaia`: ε²=0.621, q=<0.001
- `H_W2`: ε²=0.621, q=<0.001
- `J_W2`: ε²=0.613, q=<0.001
- `uw_W1_W2`: ε²=0.600, q=<0.001

Faltantes más asociados a la clase (V de Cramér; alto = la ausencia delata la clase):

- `gaia_ruwe`: V=0.786
- `gaia_mu`: V=0.786
- `gaia_parallax`: V=0.786
- `gaia_plx_snr`: V=0.786
- `gaia_BP_RP`: V=0.763
- `gaia_Cstar`: V=0.763

Variables con distribución distinta entre zonas del cielo (KS D>0.2): 19

## 4. Atajos: qué logra el modelo con información que NO debería usar

| Experimento | bal_acc CV | bal_acc repesado por brillo | recall T | recall Y | precisión Y |
|---|---|---|---|---|---|
| E1_nucleo_fisico | 0.749 | 0.649 | 0.819 | 0.350 | 0.560 |
| E1b_sin_extra | 0.708 | 0.615 | 0.810 | 0.175 | 0.233 |
| E1c_mas_paralaje_wise | 0.719 | 0.616 | 0.814 | 0.225 | 0.360 |
| E2_nucleo_mas_gaia | 0.806 | 0.721 | 0.928 | 0.375 | 0.556 |
| E3_nucleo_mas_brillo | 0.716 | 0.620 | 0.816 | 0.175 | 0.280 |
| E0_solo_atajos | 0.684 | 0.601 | 0.846 | 0.100 | 0.222 |

Lectura: E0 usa solo faltantes, separaciones de cruce, posición y brillo. Si E0 es alto, la muestra permite acertar sin física; por eso esas variables quedan fuera del modelo.

## 5. Importancia de variables (mixta)

**E1_nucleo_fisico** — 21 variables, 8 clusters, bal_acc OOF 0.750
- Cluster dominante: `cw_W1_W2+6más` (cuota 0.65)
- Boruta confirmadas: cw_W1_W2, aw_W1_W2, uw_W1_W2, J_H, H_Ks, J_Ks, J_W1, J_W2, H_W2, Ks_W2, cw_mu, cw_log_mu, Hrpm_W2, Hrpm_J, W2_W3, W1_W3, cw_W1_W2_pm, Hrpm_W2_pm, cw_mu_snr
- Consenso (rango medio de 5 métodos): uw_W1_W2, cw_W1_W2_pm, aw_W1_W2, cw_W1_W2, J_W2, Ks_W2, H_W2, cw_mu_snr

**E2_nucleo_mas_gaia** — 30 variables, 13 clusters, bal_acc OOF 0.809
- Cluster dominante: `cw_W1_W2+6más` (cuota 0.36)
- Boruta confirmadas: cw_W1_W2, aw_W1_W2, uw_W1_W2, J_H, H_Ks, J_Ks, J_W1, J_W2, H_W2, Ks_W2, cw_mu, cw_log_mu, Hrpm_W2, Hrpm_J, W1_W3, Hrpm_W2_pm, cw_mu_snr, cw_W1_W2_pm, gaia_parallax, gaia_Cstar, gaia_BP_RP, gaia_plx_snr, gaia_G_J, gaia_G_W2, gaia_M_W2, gaia_mu, W2_W3, gaia_ruwe
- Consenso (rango medio de 5 métodos): cw_W1_W2_pm, uw_W1_W2, aw_W1_W2, H_W2, gaia_parallax, gaia_BP_RP, cw_W1_W2, Ks_W2

Subanálisis T vs Y (AUC univariado, solo enanas):

- `spitzer_ch1_ch2`: AUC=0.983 (n_Y=37)
- `cw_W1_W2_pm`: AUC=0.903 (n_Y=31)
- `cw_W1_W2`: AUC=0.893 (n_Y=31)
- `Hrpm_W2_pm`: AUC=0.826 (n_Y=31)
- `Hrpm_W2`: AUC=0.821 (n_Y=31)
- `cw_log_mu`: AUC=0.779 (n_Y=32)

## 6. Dependencia de una sola variable: modelo base vs robusto

Prueba de estrés: en validación se apaga cada cluster como si esa medición faltara.

| Variante | bal_acc limpio | peor caso al apagar un cluster | cluster más crítico |
|---|---|---|---|
| base | 0.749 | 0.546 | `cw_W1_W2+6más` |
| robusto | 0.742 | 0.634 | `cw_W1_W2+6más` |

Elegido: **robusto** (robusto si mejora el peor caso de estrés y pierde <= 0.02 de bal_acc limpia).

## 7. Test espacial externo (evaluado una sola vez)

- bal_acc 0.729, macro-F1 0.756, AP T/Y 0.949
- Peso de clases: potencia 0.25 (elegida por CV, ver 05_modelo/eleccion_peso_clases.json)
- precisión Y 0.333; recall T 0.809 (IC95 [0.7486338797814208, 0.8633879781420765]), recall Y 0.300 (IC95 [0.1, 0.6])
- Umbral 'desconocido' τ=0.3: cobertura 1.000, precisión T/Y aceptadas 0.953
- Con brillo igualado: bal_acc 0.636

Estrés en test (bal_acc al apagar cada cluster):

- sin `cw_W1_W2+6más`: 0.654
- sin `cw_mu+4más`: 0.735
- sin `J_H+J_Ks+J_W1`: 0.727
- sin `W2_W3+W1_W3`: 0.707
- sin `H_Ks`: 0.723
- sin `W3_detectada`: 0.749
- sin `aw_var_w2`: 0.746
- sin `cw_mu_snr`: 0.703

## 8. SPHEREx (5 objetivos; descriptivo)

- Espectros: {'objetos': 2, 'filas_ok': 545, 'filas_total': 1591, 'uso': 'DESCRIPTIVO_N_PEQUENO; no entra al clasificador'}
- QA de FITS: {'status': 'OK', 'archivos': 1927, 'errores': 0, 'faltantes': 0}

## 8b. Extracción completa de los FITS: trayectorias y movimiento propio

Método: gaussiana 2D ponderada sobre IMAGE−ZODI; predicción con μ + paralaje anual geocéntrico. Estado: DEGRADED_GAUSS_NO_EPSF: posiciones aproximadas; validar con ePSF del motor.

| Objetivo | Exposiciones | Limpias | μα* catálogo | μα* medido | μδ catálogo | μδ medido | residuo mediano |
|---|---|---|---|---|---|---|---|
| Barnard's Star | 364 | 0 | -802 | — | 10362 | — | —″ |
| Epsilon Indi B | 421 | 314 | 3982 | 3916 ± 11 | -2467 | -2543 ± 13 | 0.80″ |
| R Draconis | 548 | 0 | -21 | — | 6 | — | —″ |
| RW Aurigae | 336 | 18 | 3 | 160 ± 52 | -27 | 137 ± 48 | 0.50″ |
| WISE 0855-0714 | 258 | 44 | -8124 | 876 ± 297 | 673 | -383 ± 263 | 7.40″ |

μ en mas/año. 'Medido' = catálogo + pendiente de los residuos. Figuras en 07_extraccion_fits/figuras/.

## 9. Advertencias registradas

- E1_nucleo_fisico: el cluster 'cw_W1_W2+6más' concentra 65% de la importancia
- ATAJO: solo faltantes/brillo/posición logran bal_acc 0.68; la muestra trae sesgo de construcción

## 10. Límites honestos

- Solo 50 Y en total: los intervalos de recall Y son anchos; no hay modelo final 'validado' para Y.
- Las estrellas de control vienen de 40 campos Gaia: su brillo y su posición no representan el cielo.
- SPHEREx cubre 5 objetos: no entra al clasificador; los índices son de control.
- Paralaje del observador no corregido en las posiciones de SPHEREx (heredado del piloto).
- La importancia predictiva no implica causa física.
