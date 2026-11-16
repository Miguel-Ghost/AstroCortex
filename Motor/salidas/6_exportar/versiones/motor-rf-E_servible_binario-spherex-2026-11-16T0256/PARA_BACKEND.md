# Modelo para el backend (motor-rf-E_servible_binario-spherex-2026-11-16T0256)

- Archivo: `model.onnx` + `metadata.json` (copiar ambos a la ruta que lee `load_predictor`).
- Modelo: rf del experimento E_servible_binario; clases ['star', 'cold_brown_dwarf']; umbral cold_brown_dwarf = 0.5.
- Verificación ONNX vs original en test: diferencia máxima 3.39e-07, acuerdo de clase 1.000.

## Evidencia que el backend debe calcular por fuente (mismos nombres)

| feature | definición |
|---|---|
| `cw_W1_W2` | CatWISE2020 w1mpro − w2mpro [mag Vega]; NaN si cc_flags/ab_flags de W1 o W2 ≠ '0' |
| `cw_mu` | hypot(pmra, pmdec) de CatWISE2020 [arcsec/año] (pmra/pmdec de CatWISE vienen en arcsec/año) |
| `Hrpm_W2` | w2mpro + 5·log10(max(cw_mu, 0.005)) + 5 [mag]; movimiento propio reducido |
| `spx_c21` | −2.5·log10(F_D2/F_D1), flujos SPHEREx con ajuste de PSF gaussiana; solo si S/N ≥ 3 en ambos |
| `spx_c32` | −2.5·log10(F_D3/F_D2), misma regla |
| `spx_c43` | −2.5·log10(F_D4/F_D3), misma regla |
| `spx_c54` | −2.5·log10(F_D5/F_D4), misma regla |
| `spx_c65` | −2.5·log10(F_D6/F_D5), misma regla |
| `spx_c64` | −2.5·log10(F_D6/F_D4), misma regla |
| `spx_ch4` | log10(F_D5/F_D4) = log10(methane_index del backend); con D5 S/N≥3 y D4 S/N<3: log10(F_D5/(3·σ_D4)) |

Si una feature no existe para una fuente, el backend usa `fill_values` (mediana de entrenamiento).
Con todas las features faltantes este modelo responde cold_brown_dwarf (star 0.22, cold_brown_dwarf 0.78), porque los valores de relleno son medianas de un subconjunto con 42 % de enanas frías: el backend debe marcar como `insufficient_data` las fuentes sin `cw_W1_W2` (la variable que más pesa) en vez de usar la predicción.
Las reglas de `jpl_match` (asteroide) y `extended` (galaxia) no las aprende este modelo: conviene aplicarlas antes del modelo, como hace `RulePredictor`.
