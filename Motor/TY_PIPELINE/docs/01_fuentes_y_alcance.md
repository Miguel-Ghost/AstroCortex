# Fuentes y alcance

Regla: solo datos que ya existen en `SpaceApps2026_Reto`. Nada se descarga en esta versión.

## Usado

| Fuente | Archivo local | Uso |
|---|---|---|
| UltracoolSheet v2.0 (Zenodo, CC-BY-4.0) | `data/raw/ultracoolsheet/` | etiquetas M/L/T/Y; ch1/ch2 de Spitzer solo para subanálisis T vs Y |
| Gaia DR3 (ESA TAP) | `data/processed/xm_gaia.parquet` | estrellas de control; grupo `gaia` aparte (E2) |
| CatWISE2020, AllWISE, 2MASS PSC, unWISE (NOIRLab Data Lab, mismos catálogos que IRSA) | `CLASIFICADOR_TY/data/catalogos_noirlab/` | colores, μ, movimiento propio reducido; recibos SHA verificados |
| SPHEREx DR1/QR3 (IRSA SIA + S3) | `spherex_raw_mef/`, `spherex_phot_targets.parquet` | 1927 MEF de 5 objetivos piloto: QA y espectros descriptivos |

## Tutoriales IRSA (https://caltech-ipac.github.io/irsa-tutorials/)

Son recetas de acceso, no datos.

| Sección | Estado en esta versión |
|---|---|
| SPHEREx | usado (piloto de 5 objetos); el visor/flipbook es otro entregable |
| WISE | usado vía NOIRLab (mismos catálogos). Cambiar a IRSA TAP no cambia los valores |
| Spitzer | solo ch1/ch2 de UltracoolSheet, que existen solo para enanas → no sirven contra estrellas |
| Euclid, COSMOS, ZTF | no hay datos locales. Además: Euclid y COSMOS cubren poca área con pocas T/Y; ZTF es óptico y las T/Y casi no se ven |
| Simulated Data | no se mezcla con etiquetas reales; solo serviría para probar código (aquí se usa un generador sintético propio) |
| Techniques & Tools | métodos (cruces, recortes), no datos |

## CatNorth (arXiv:2310.12704, §3)

Se toma el método: colores con WISE, C* de Gaia (Riello+2021), contaminantes difíciles en el
entrenamiento y validación cruzada. No se copian sus 14 rasgos: dependen de Pan-STARRS y Gaia,
donde las Y casi nunca aparecen. CatNorth usa XGBoost; aquí se usa `HistGradientBoosting`
(misma familia, maneja NaN de forma nativa y ya viene en scikit-learn).
