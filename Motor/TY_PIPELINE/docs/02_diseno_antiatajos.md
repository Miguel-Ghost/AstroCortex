# Diseño antiatajos: por qué un modelo que depende de una variable falla

## El problema

Si un modelo aprende casi todo de una variable (o de un grupo de variables gemelas), cuando esa
medición falta, es ruidosa o se comporta distinto en otra zona del cielo, el modelo falla, aunque
existan otras variables relacionadas que podrían haberlo salvado. Ocurre porque el entrenamiento
nunca "obligó" al modelo a usar esas otras rutas.

Además, en esta muestra hay variables que separan las clases **por cómo se construyó la tabla**, no por
física. Un modelo que las use aprende la receta de la tabla, y falla con objetos reales.

## Atajos de construcción detectados en los datos

| Variable | Por qué delata la clase |
|---|---|
| `epoch` | Las 8000 estrellas tienen 2016.0 (vienen de Gaia); las enanas tienen épocas de literatura |
| `source`, `gaia_field` | Indican directamente de qué lista salió el objeto |
| `gaia_source_id` / "tiene Gaia" | 100 % de estrellas está en Gaia por construcción; muchas T y casi todas las Y no |
| `plx`, `pmra`, `pmdec` de `objects` | Procedencia distinta por clase; se usa el μ medido por CatWISE, igual para todos |
| `ucs_W1`, `ucs_W2`, `sptnum`, `spt_*` | Solo existen para enanas, o son la etiqueta misma |
| Separación del cruce | Las posiciones de las enanas se propagaron con μ de literatura; las de Gaia son exactas |
| Brillo aparente (W2, J, SNR) | Los 40 campos de estrellas tienen otra distribución de brillo que las enanas cercanas |
| Posición / latitud galáctica | Las estrellas están en 40 campos; las enanas en todo el cielo |

Todas quedan en `OBJECTS_FORBIDDEN` (`typipe/data.py`) o en grupos `AUDIT_*` (`typipe/s1_features.py`).

## Controles

1. **E0 solo atajos**: el modelo ve solo faltantes, separaciones, posición y brillo. Su balanced accuracy es
   la vara de "cuánto se puede acertar sin física".
2. **E3 vs E1**: cuánto sube el acierto al añadir brillo aparente. Si sube, era atajo.
3. **Repesado por brillo**: se evalúa dando a estrellas/M/L la misma distribución de W2 que a T/Y.
4. **Partición espacial**: celdas enteras del cielo van a validación o a test; nada se mezcla.
5. **Clusters** (|Spearman| ≥ 0.8): importancia por permutación del grupo completo, y ablación reentrenando sin el grupo.
6. **Cuota de dominancia**: si un cluster concentra más del 50 % de la importancia, se registra una advertencia.
7. **Prueba de estrés**: se apaga cada cluster en validación y en test (como si esa medición faltara).
8. **Entrenamiento con apagado de grupos** (variante robusta): copias del entrenamiento donde cada cluster se
   vuelve NaN con probabilidad 0.3, y el cluster dominante en la mitad de las filas de la mitad de las copias.
   `HistGradientBoosting` maneja NaN de forma nativa, así que aprende qué hacer cuando falta cada grupo.
9. **Regla de elección escrita antes de ver resultados**: robusto si mejora el peor caso de estrés y no pierde
   más de 0.02 de balanced accuracy limpia.

## Qué pasó en la prueba sintética

Con datos falsos donde W1−W2 es muy informativo, el modelo base caía de 0.925 a 0.505 de balanced accuracy
al faltar W1−W2. El robusto mantenía 0.924 limpio y subía el peor caso a 0.629. El resultado real está en
`resultados_TY/run_001/INFORME.md`.
