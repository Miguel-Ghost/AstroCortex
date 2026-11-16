# TY_PIPELINE — clasificador de enanas T/Y frente a estrellas (solo datos existentes)

Versión 1.0.0 · 2026-11-15. Este paquete reemplaza a `EJECUTAR_ANALISIS_TY.py` para el análisis.
No descarga nada: trabaja con lo que ya está en `SpaceApps2026_Reto`, que trata como **solo lectura**.
Todo lo que produce queda en `NASA SPACE APPS\CLASIFICADOR_TY\resultados_TY\<run_id>\`.

## Cómo se ejecuta (Windows)

```
windows\01_instalar_entorno.bat     (una vez; crea .venv propio del clasificador)
windows\02_ejecutar_pipeline.bat    (todas las etapas; se puede repetir: reanuda)
windows\03_ver_estado.bat           (resumen de ESTADO.json)
windows\04_prueba_sintetica.bat     (prueba con datos falsos, no toca los reales)
```
En Git Bash: `./ejecutar.sh` (equivalente a 01+02). Opciones: `--stages 03_eda 05_modelo`, `--force`.

## Estructura

| Carpeta | Contenido |
|---|---|
| `config/config.json` | rutas, semilla, umbrales y reglas fijadas antes de ver resultados |
| `typipe/` | código: `s0_inventory` … `s7_report`, `ml.py`, `data.py`, `common.py` |
| `tests/` | generador sintético y prueba de punta a punta |
| `windows/`, `ejecutar.sh` | lanzadores |
| `docs/` | fuentes y alcance, diseño antiatajos, ingeniería de imágenes |
| `coordinacion/` | protocolo de trabajo con Claude Code y Codex |

## Etapas y salidas (`resultados_TY/run_001/`)

| Etapa | Qué hace | Archivos principales |
|---|---|---|
| `00_inventario` | hashes de entradas, clases, FITS en disco vs índice | `inventario.json` |
| `01_variables` | cruce más cercano (≤3″) de CatWISE/AllWISE/2MASS/unWISE, limpieza igual para todas las clases, colores, movimiento propio reducido, Gaia aparte | `features.parquet`, `diccionario_variables.json`, `feature_groups.json`, `calidad_cruces.json` |
| `02_particion` | celdas del cielo de área igual; 20 % de celdas = test externo; 5 pliegues espaciales | `particion.parquet`, `particion_resumen.json` |
| `03_eda` | A) descripción de todas las columnas de todas las tablas; B) por clase solo en desarrollo: normalidad, Kruskal+ε², Mann–Whitney+Cliff, χ² de faltantes+V de Cramér, KS entre zonas, Spearman, BH | `A_descriptivo_tablas/`, `B_pruebas.csv`, `figuras/` |
| `04_importancia` | permutación por cluster e individual, ablación por cluster, información mutua, Boruta, consenso, cuota de dominancia, subanálisis T vs Y (Spitzer) | `E1_*/consenso.csv`, `importancia_resumen.json` |
| `05_modelo` | experimentos de atajos E0–E3, base vs robusto, prueba de estrés, umbral `desconocido`, test externo una sola vez | `experimentos.json`, `prueba_estres.csv`, `modelo_final.json/.pkl` |
| `06_spherex` | espectros e índices CH₄/H₂O/CO de los 5 pilotos; QA de los 1927 MEF | `indices_espectrales_piloto.csv`, `fits_qa.csv` |
| `07_informe` | informe legible | `INFORME.md` |

`ESTADO.json` resume en pocas líneas qué etapa terminó, cuál falló y por qué. Es lo único que hace falta leer para supervisar.

## Idea central: que el modelo no dependa de una sola variable

Ver `docs/02_diseno_antiatajos.md`. En resumen:
1. Se prohíben las columnas que delatan cómo se armó la muestra (época, procedencia, "tiene Gaia", paralaje de literatura…).
2. Se mide cuánto acierta un modelo **solo con atajos** (E0). Si acierta mucho, la muestra está sesgada y esas variables quedan fuera.
3. Las variables correlacionadas se agrupan; la importancia se mide por grupo, porque una variable gemela tapa a la otra.
4. **Prueba de estrés**: se apaga cada grupo en validación. Un modelo que se derrumba sin un grupo es frágil.
5. **Modelo robusto**: se entrena apagando grupos al azar y el grupo dominante en la mitad de las copias, para que aprenda rutas de respaldo. Se elige con una regla escrita de antemano en `config.json`.

## Límites

- 50 Y en total: el recall de Y tiene intervalos anchos.
- SPHEREx cubre 5 objetos: descriptivo, no entra al modelo.
- Euclid, COSMOS, ZTF y datos simulados no existen localmente; no se usan.
- La importancia predictiva no prueba causa física.
