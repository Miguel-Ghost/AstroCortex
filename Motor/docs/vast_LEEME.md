> Dentro de AstroCortex este paquete es la carpeta `Motor/`: los scripts `instalar.sh`, `ejecutar_todo.sh`, `ver_estado.sh` y `empaquetar_salidas.sh` están en `Motor/scripts/` y se ejecutan desde `Motor/` (por ejemplo `scripts/ejecutar_todo.sh --modelos`).

# Clasificador AstroCortex en Vast: descarga, preprocesamiento, modelos y ONNX

Versión 1.0 · 15 nov 2026. Para: Miguel (ejecución en la máquina Vast). Backend y contrato del modelo: Brian.

Este paquete corre en una máquina alquilada en Vast todo el camino del motor clasificatorio:

1. descarga de datos SPHEREx directamente en la máquina;
2. gestión y cruce de datos;
3. EDA;
4. preprocesamiento: duplicados, faltantes, outliers y balanceo;
5. variables nuevas e importancia de variables;
6. partición entrenamiento/validación/test;
7. comparación de Random Forest, XGBoost y red neuronal;
8. exportación del modelo elegido en el formato que carga el backend (`model.onnx` + `metadata.json`).

Partes del paquete:

- **`TY_PIPELINE/`**: el pipeline de Paolo, sin cambios en el código. Cruza los catálogos, arma la partición espacial y hace el EDA y la importancia de variables.
- **`motor/`**: el código nuevo. Descarga SPHEREx, preprocesa, compara los modelos y exporta.
- **`notebooks/`**: notebooks para mirar los resultados.
- **`config/motor.json`**: todos los parámetros en un solo lugar.

---

## 1. Contenido

```
CLASIFICADOR_VAST/
├── LEEME.md                  este archivo
├── CONEXION_VAST.md          conexión por SSH, tmux, Jupyter y cómo devolver resultados
├── instalar.sh               entorno .venv (Python 3.13) + pruebas de humo + prueba de red
├── ejecutar_todo.sh          lanzador (modos: todo, --rapido, --descargas, --modelos)
├── ver_estado.sh             resumen del avance (TY y motor)
├── empaquetar_salidas.sh     zip con lo que hay que devolver
├── requirements.txt
├── config/motor.json         parámetros del motor (selección, concurrencia, modelos, experimentos)
├── motor/                    código del motor (python -m motor)
├── tests/                    prueba sintética sin red de las etapas SPHEREx y verificación de red
├── notebooks/                01 exploración · 02 preprocesamiento · 03 comparación de modelos
├── TY_PIPELINE/              pipeline de Paolo: variables de catálogo, partición, EDA, importancia
├── datos_entrada/            objects.parquet (11 850 objetos con etiqueta), cruces, lotes NOIRLab con recibos
├── datos_extra_TY/           CatWISE completo (σμ, *_pm, paralaje) y AllWISE W3/W4
└── resultados_TY/run_003/    corrida anterior de TY (referencia y respaldo)
```

Se generan en la máquina:

- `.venv/`;
- `logs/`;
- `resultados_TY/run_004/` (la corrida nueva de TY);
- `salidas/` (todo lo del motor).

## 2. Orden de trabajo en la máquina

Comandos dentro de la máquina, en `/workspace/CLASIFICADOR_VAST`. La conexión está en `CONEXION_VAST.md`.

```bash
cd /workspace && unzip CLASIFICADOR_VAST.zip && cd CLASIFICADOR_VAST
chmod +x *.sh
./instalar.sh                      # ~5-10 min; termina con "RESULTADO: OK" (prueba sin red) y con la prueba de IRSA y S3
tmux new -s clasificador           # todo lo largo va dentro de tmux
```

Dentro de tmux se abren dos ventanas (Ctrl+b y luego c crea una ventana; Ctrl+b y luego 0 o 1 cambia entre ellas):

```bash
# ventana 0: descargas SPHEREx (red)
./ejecutar_todo.sh --descargas

# ventana 1: TY + primer modelo solo con catálogo (CPU), en paralelo
./ejecutar_todo.sh --rapido
```

Cuando termina `--descargas` (en `ver_estado.sh` la etapa `3_features_spherex` aparece en OK), se rehacen los modelos con SPHEREx:

```bash
./ejecutar_todo.sh --modelos
./empaquetar_salidas.sh            # zip para devolver al equipo
```

Con `--rapido` el resumen global del motor queda en PARCIAL porque las etapas 1–3 siguen pendientes. Es lo esperado.

Si la sesión SSH se corta, tmux sigue corriendo. Para volver: `tmux attach -t clasificador`. Para mirar el avance desde otra terminal: `./ver_estado.sh`.

### Tiempos aproximados

Son estimaciones. Dependen de la máquina y de cómo responda IRSA.

| Paso | Qué limita | Estimado |
|---|---|---|
| `instalar.sh` | descarga de paquetes | 5–10 min |
| TY 00–03 | CPU | < 1 min |
| TY 04 importancia | CPU | 5–15 min |
| motor 4–7 sin SPHEREx (`--rapido`) | CPU | 30–50 min |
| motor 1 índice SIA (~3000 objetos × 2 colecciones) | IRSA, 4 consultas a la vez | 40–80 min |
| motor 2 fotometría (~70 000 lecturas parciales de S3) | red de la máquina, 32 hilos | 40–80 min |
| motor 4–7 con SPHEREx (`--modelos`) | CPU | 40–60 min |

El primer modelo exportable (solo catálogo) está en `salidas/6_exportar/` cuando termina `--rapido`. Cada exportación queda también en `salidas/6_exportar/versiones/<versión>/`, así una corrida posterior no pisa la anterior.

## 3. Qué hace cada etapa

| Etapa | Comando | Qué hace | Salida principal |
|---|---|---|---|
| TY 00 inventario | `ejecutar_todo.sh` | hashes de entradas, clases | `resultados_TY/run_004/00_inventario/` |
| TY 01 variables | idem | **cruce** con CatWISE, AllWISE, 2MASS, unWISE (candidato más cercano ≤ 3″) y Gaia aparte; limpieza igual para todas las clases; colores y movimiento propio reducido | `01_variables/features.parquet` |
| TY 02 partición | idem | celdas de cielo de igual área; 20 % de celdas = test externo; 5 pliegues espaciales en desarrollo | `02_particion/particion.parquet` |
| TY 03 EDA | idem | descripción de todas las tablas; pruebas por clase (Kruskal, Mann-Whitney, χ² de faltantes, Spearman) solo en desarrollo | `03_eda/` |
| TY 04 importancia | idem | permutación por grupo, ablación, información mutua, Boruta, consenso | `04_importancia/` |
| motor 1 | `--descargas` | **descarga**: índice SPHEREx por objeto (IRSA SIA); posición igual para todas las clases (CatWISE); quita duplicados DR1/QR3 | `salidas/1_indice_spherex/` |
| motor 2 | `--descargas` | **descarga**: 15×15 px por exposición desde S3; fotometría forzada con PSF; máscara de FLAGS | `salidas/2_fotometria_spherex/` |
| motor 3 | `--descargas` | **feature engineering** SPHEREx: colores entre detectores y metano (D5/D4) | `salidas/3_features_spherex/` |
| motor 4 | `--rapido` / `--modelos` | **preprocesamiento**: duplicados, valores imposibles, faltantes, outliers, balance | `salidas/4_preprocesamiento/` |
| motor 5 | idem | **RF vs XGBoost vs MLP** con CV espacial; importancia por permutación; test una vez | `salidas/5_modelos/` |
| motor 6 | idem | **ONNX + metadata.json** del modelo servible; verificación con onnxruntime y simulación del backend | `salidas/6_exportar/` |
| motor 7 | idem | informe y manifiesto con SHA-256 | `salidas/INFORME_MOTOR.md` |

Cada etapa se corre sola con `python -m motor --etapas <nombre>` (con `.venv` activado).

## 4. Experimentos (config `experimentos`)

| Experimento | Variables | Clases | Población | Para qué |
|---|---|---|---|---|
| A_catalogo_5clases | núcleo físico de TY (21) | star, M, L, T, Y | todos | referencia científica, comparable con el informe de TY |
| B_catalogo_binario | núcleo físico de TY | star (estrella+M+L) vs cold_brown_dwarf (T+Y) | todos | lo que el producto necesita: "¿enana fría o no?" |
| C_catalogo_5clases_subconjunto | núcleo físico de TY | 5 clases | objetos con SPHEREx | base para medir cuánto aporta SPHEREx (mismas filas que D) |
| D_catalogo_spherex_5clases | núcleo físico + colores SPHEREx | 5 clases | objetos con SPHEREx | aporte de SPHEREx: comparar con C |
| E_servible_binario | solo lo que el backend calcula por fuente: cw_W1_W2, cw_mu, Hrpm_W2 + colores SPHEREx | binario | con SPHEREx (o todos si no hay) | **el que se exporta** |

El modelo exportado tiene que usar variables que el backend pueda calcular para cualquier fuente del visor. El backend tiene CatWISE y su propia fotometría SPHEREx, pero no 2MASS. Por eso el experimento E usa menos variables que A y B.

## 5. Decisiones fijadas antes de mirar el test

Están en el código y en `config/motor.json`. No se cambian después de ver resultados del test.

- **Partición:** la espacial de TY (celdas enteras de cielo). Validación = 5 pliegues de desarrollo. Test = 20 % de celdas, evaluado una vez.
- **Duplicados:**
  - mismo objeto con dos `oid` (< 2″ tras propagar a 2016.0) o mismo vector de variables: si la etiqueta coincide, queda el `oid` menor; si difiere, se quitan todos;
  - en SPHEREx, la misma exposición en DR1 y QR3 queda una sola vez (se prefiere DR1).
- **Valores imposibles → faltante:** colores con |valor| > 15 mag y μ > 20″/año.
- **Faltantes:**
  - se imputan con la mediana del entrenamiento de cada pliegue, la misma que el backend usa como `fill_values`;
  - sin indicadores de "falta": en esta muestra la ausencia de catálogo delata cómo se armó la tabla (experimento E0 de TY: 0.68 de balanced accuracy solo con atajos);
  - se quitan variables con > 97 % de faltantes en desarrollo.
- **Outliers:** se cuentan e informan por clase (z robusto > 6) y no se borran, porque un extremo de color puede ser una Y. La red recorta a los percentiles 0.5–99.5 dentro de su grafo.
- **Balanceo:**
  - pesos por clase (N/(K·n_c))^p, con p elegido por CV entre 1, 0.5 y 0.25;
  - sin remuestreo ni SMOTE: con 50 Y, SMOTE fabrica vecinos de pocos puntos.
- **Elección del modelo:** mayor macro-F1 en la CV espacial de desarrollo.
- **Umbral de la clase fría (unknown):** menor probabilidad que da ≥ 90 % de precisión fuera de pliegue.
- **Variables que nunca entran:**
  - identificadores, procedencia, época, paralaje o movimiento de `objects.parquet`;
  - "tiene Gaia";
  - brillo aparente y S/N: SPHEREx los guarda como auditoría (`spx_snr_max`, `spx_n_det`), no como predictores.

## 6. Ajustes frecuentes (config/motor.json)

| Clave | Por defecto | Cuándo cambiar |
|---|---|---|
| `spherex.seleccion_por_clase` | star 800, M 400, L 800, T todos, Y todos | más objetos = más tiempo de descarga (lineal) |
| `spherex.exposiciones_por_detector` | 4 | 3 reduce la fotometría un 25 % |
| `spherex.sia_concurrencia` | 4 | bajar a 2 si IRSA devuelve muchos 429/503 |
| `spherex.s3_concurrencia` | 32 | bajar a 16 si la máquina se satura; subir a 64 con buena red |
| `modelos.potencias_peso_clase` | [1, 0.5, 0.25] | dejar [0.25] para ir más rápido (TY eligió 0.25) |
| `modelos.mlp.capas` | [128, 64] | arquitectura de la red |

Si la selección se cambia después de empezar las descargas, hay que borrar `salidas/1_indice_spherex/seleccion.parquet` y `salidas/2_fotometria_spherex/plan.parquet`. Las cachés de objetos ya consultados se reutilizan.

## 7. Qué devolver

`./empaquetar_salidas.sh` arma `ENTREGA_CLASIFICADOR_<fecha>.zip`. Ese zip va al Drive o directo a Brian. Lo mínimo para el backend:

- `salidas/6_exportar/model.onnx`;
- `salidas/6_exportar/metadata.json`;
- `salidas/6_exportar/PARA_BACKEND.md`: qué variables tiene que calcular el backend por fuente, con su fórmula;
- `salidas/INFORME_MOTOR.md` y `salidas/5_modelos/comparacion_global.csv`: resultados de la comparación.

## 8. Problemas frecuentes

| Síntoma | Qué hacer |
|---|---|
| `ver_estado.sh` muestra FALLO | leer `error` y `traceback` en `salidas/ESTADO.json`; relanzar el mismo modo |
| Muchos `ERROR_LECTURA` o errores SIA | relanzar `--descargas`: reintenta solo lo pendiente; bajar la concurrencia si se repite |
| IRSA no responde (prueba de red falla) | correr `--rapido` mientras tanto; el modelo de catálogo no necesita IRSA |
| TY falla en run_004 | el motor usa solo `resultados_TY/run_003` (misma partición, semilla fija) |
| Se cortó la máquina | al reanudar, `--descargas` sigue desde la caché; `--modelos` se rehace completo |
| Los notebooks no encuentran archivos | abrirlos desde `notebooks/` con el kernel "Clasificador (.venv)"; usan lo que haya en `salidas/` |

## 9. Notebooks

Son de solo lectura sobre lo que generan las etapas. Se abren con Jupyter por túnel SSH (ver `CONEXION_VAST.md`).

- `01_exploracion_datos.ipynb`: clases, procedencia, faltantes por clase, distribuciones, variables SPHEREx y mapa dev/test.
- `02_preprocesamiento.ipynb`: duplicados, faltantes, outliers, balance y tabla final.
- `03_comparacion_modelos.ipynb`: tabla RF/XGB/MLP, matrices de confusión, importancia y modelo exportado.

## 10. Límites conocidos

- 50 Y en total: el recall de Y tiene intervalos anchos.
- Las estrellas de control vienen de 40 campos de Gaia: su brillo y su posición no representan el cielo.
- Cada exposición SPHEREx mide otra λ dentro del detector (filtro LVF). Los colores por detector mezclan λ, igual que los coadds del backend.
- La fotometría del entrenamiento (por exposición) y la del backend (coadds) usan la misma PSF por detector, pero no son idénticas. Conviene comparar los 5 objetivos piloto: `salidas/3_features_spherex/controles_pilotos.csv` contra `/api/sources`.
- Las clases galaxia y asteroide no están en los datos de entrenamiento. En el backend siguen saliendo de las reglas (`extended`, `jpl_match`).
