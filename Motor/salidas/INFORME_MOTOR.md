# Informe del motor clasificatorio (Vast)

Generado: 2026-11-16T02:56:21+00:00. Fuente de cada cifra: carpeta `salidas/`.

## 1. Datos SPHEREx descargados

- Objetos seleccionados: 855; con exposiciones: 834; sin respuesta SIA: 21.
- Filas del índice: 240384 (duplicados entre colecciones quitados: 0); exposiciones por objeto (mediana): 267.0; épocas (mediana): 3.0.
- Lecturas: 15012; estados: {'OK': 14189, 'NUCLEO_ENMASCARADO': 668, 'SIN_FONDO': 140, 'FUERA_DEL_DETECTOR': 15}.
- S/N mediana por detector: {'1': 3.68, '2': 9.62, '3': 10.77, '4': 8.51, '5': 5.04, '6': 2.3}.
- Objetos con alguna medición OK: 826 de 850.

Cobertura de colores SPHEREx por clase (fracción no faltante):

```
      spx_c21  spx_c32  spx_c43  spx_c54  spx_c65  spx_c64  spx_ch4
L       0.615    0.880    0.880    0.850    0.680    0.675    0.850
M       0.850    0.910    0.910    0.910    0.890    0.870    0.910
T       0.233    0.377    0.370    0.427    0.380    0.277    0.690
Y       0.100    0.160    0.160    0.200    0.300    0.120    0.540
star    0.975    0.970    0.875    0.635    0.475    0.470    0.635
```

## 2. Preprocesamiento

- Filas: 11850 → 11815 (duplicados quitados: 35).
- Valores imposibles pasados a faltante: ninguno.
- Variables quitadas por faltantes: ninguna.
- Variables por conjunto: {'catalogo': 21, 'catalogo_mas_spherex': 28, 'servible': 10}.
- Outliers marcados (no borrados): 1107.
- TY_PIPELINE usado: `/workspace/CLASIFICADOR_VAST/resultados_TY/run_004`.
- Balance (desarrollo/test): {'5clases': {'dev': {'star': 6371, 'L': 1563, 'M': 736, 'T': 735, 'Y': 40}, 'test': {'star': 1599, 'L': 394, 'M': 184, 'T': 183, 'Y': 10}, 'dev_subconjunto_spherex': {'T': 251, 'L': 167, 'star': 160, 'M': 79, 'Y': 40}}, 'servible': {'dev': {'star': 8670, 'cold_brown_dwarf': 775}, 'test': {'star': 2177, 'cold_brown_dwarf': 193}, 'dev_subconjunto_spherex': {'star': 406, 'cold_brown_dwarf': 291}}}
- Estrategia: pesos por clase (N/(K·n_c))^p, p elegido por CV entre [0.25]; sin remuestreo ni SMOTE.

## 3. Comparación de modelos (CV espacial; test una vez)

```
                   experimento modelo  elegido_por_cv  potencia_peso  n_variables  cv_macro_f1  cv_balanced_accuracy  cv_ap_positivas  cv_recall_positivas  test_macro_f1  test_balanced_accuracy  test_ap_positivas  test_recall_positivas  test_precision_positivas
            A_catalogo_5clases     rf           False           0.25           21       0.7531                0.7241           0.9257               0.8297         0.7532                  0.7215             0.9414                 0.8394                    0.9419
            A_catalogo_5clases    xgb            True           0.25           21       0.7808                0.7528           0.9257               0.8374         0.7814                  0.7625             0.9456                 0.8394                    0.9205
            A_catalogo_5clases    mlp           False           0.25           21       0.7469                0.7291           0.9149               0.8335         0.7539                  0.7289             0.9444                 0.8446                    0.9261
            B_catalogo_binario     rf            True           0.25           21       0.9384                0.9129           0.9277               0.8297         0.9359                  0.9122             0.9385                 0.8290                    0.9412
            B_catalogo_binario    xgb           False           0.25           21       0.9377                0.9151           0.9254               0.8348         0.9326                  0.9162             0.9459                 0.8394                    0.9153
            B_catalogo_binario    mlp           False           0.25           21       0.9378                0.9157           0.9311               0.8361         0.9316                  0.9184             0.9405                 0.8446                    0.9056
C_catalogo_5clases_subconjunto     rf            True           0.25           21       0.7500                0.7325           0.9845               0.9656         0.7729                  0.7480             0.9951                 0.9661                    0.9500
C_catalogo_5clases_subconjunto    xgb           False           0.25           21       0.7358                0.7203           0.9850               0.9347         0.7922                  0.7602             0.9898                 0.9661                    0.9344
C_catalogo_5clases_subconjunto    mlp           False           0.25           21       0.7181                0.7156           0.9757               0.8660         0.7259                  0.7258             0.9780                 0.8475                    0.9615
    D_catalogo_spherex_5clases     rf            True           0.25           28       0.7563                0.7433           0.9879               0.9485         0.8325                  0.8066             0.9934                 0.9661                    0.9344
    D_catalogo_spherex_5clases    xgb           False           0.25           28       0.7459                0.7325           0.9869               0.9588         0.8295                  0.8002             0.9910                 0.9661                    0.9661
    D_catalogo_spherex_5clases    mlp           False           0.25           28       0.7385                0.7297           0.9785               0.8969         0.7743                  0.7595             0.9858                 0.9153                    0.9310
            E_servible_binario     rf            True           0.25           10       0.9455                0.9457           0.9830               0.9381         0.9583                  0.9583             0.9924                 0.9492                    0.9492
            E_servible_binario    xgb           False           0.25           10       0.9410                0.9410           0.9818               0.9313         0.9651                  0.9637             0.9927                 0.9492                    0.9655
            E_servible_binario    mlp           False           0.25           10       0.9197                0.9165           0.9741               0.8797         0.9501                  0.9407             0.9913                 0.8814                    1.0000
```

- A_catalogo_5clases: OK, elegido xgb → test {'balanced_accuracy': 0.7625, 'macro_f1': 0.7814, 'ap_positivas': 0.9456, 'precision_positivas': 0.9205, 'recall_positivas': 0.8394, 'recall_star': 0.9919, 'recall_M': 0.6467, 'recall_L': 0.8706, 'recall_T': 0.8033, 'recall_Y': 0.5}
- B_catalogo_binario: OK, elegido rf → test {'balanced_accuracy': 0.9122, 'macro_f1': 0.9359, 'ap_positivas': 0.9385, 'precision_positivas': 0.9412, 'recall_positivas': 0.829, 'recall_star': 0.9954, 'recall_cold_brown_dwarf': 0.829}
- C_catalogo_5clases_subconjunto: OK, elegido rf → test {'balanced_accuracy': 0.748, 'macro_f1': 0.7729, 'ap_positivas': 0.9951, 'precision_positivas': 0.95, 'recall_positivas': 0.9661, 'recall_star': 0.9487, 'recall_M': 0.5714, 'recall_L': 0.7812, 'recall_T': 0.9388, 'recall_Y': 0.5}
- D_catalogo_spherex_5clases: OK, elegido rf → test {'balanced_accuracy': 0.8066, 'macro_f1': 0.8325, 'ap_positivas': 0.9934, 'precision_positivas': 0.9344, 'recall_positivas': 0.9661, 'recall_star': 1.0, 'recall_M': 0.619, 'recall_L': 0.875, 'recall_T': 0.9388, 'recall_Y': 0.6}
- E_servible_binario: OK, elegido rf → test {'balanced_accuracy': 0.9583, 'macro_f1': 0.9583, 'ap_positivas': 0.9924, 'precision_positivas': 0.9492, 'recall_positivas': 0.9492, 'recall_star': 0.9674, 'recall_cold_brown_dwarf': 0.9492}

## 4. Modelo exportado al backend

- Versión: `motor-rf-E_servible_binario-spherex-2026-11-16T0256`; features: ['cw_W1_W2', 'cw_mu', 'Hrpm_W2', 'spx_c21', 'spx_c32', 'spx_c43', 'spx_c54', 'spx_c65', 'spx_c64', 'spx_ch4']; clases: ['star', 'cold_brown_dwarf']; umbrales: {'cold_brown_dwarf': 0.5}.
- Verificación ONNX: True (dif. máx. 3.3872626226116864e-07).

## 5. Límites

- 50 Y en total: el recall de Y tiene intervalos anchos (ver ic95 en metricas.json).
- Las estrellas de control vienen de 40 campos de Gaia: su brillo y posición no representan el cielo (ver atajos E0/E3 en el informe de TY_PIPELINE).
- Los colores SPHEREx mezclan λ dentro de cada detector (cada exposición mide otra λ del filtro LVF), igual que los coadds del backend.
- La importancia por permutación es predictiva, no causal.
