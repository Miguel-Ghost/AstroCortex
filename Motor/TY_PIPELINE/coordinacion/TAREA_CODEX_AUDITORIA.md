# Tarea para Codex: auditoría independiente del clasificador T/Y

Eres el auditor independiente. NO modifiques archivos de `CLASIFICADOR_TY/TY_PIPELINE/typipe`, `config`
ni `resultados_TY`. Solo escribe `CLASIFICADOR_TY/TY_PIPELINE/coordinacion/AUDITORIA_CODEX.md`.
Lee primero `coordinacion/PROTOCOLO.md`, `README.md` y `docs/02_diseno_antiatajos.md`.

Revisa, con evidencia (archivo:línea o valor de un resultado):

1. **Fuga de información**: ¿alguna columna de `OBJECTS_FORBIDDEN` o de los grupos `AUDIT_*` entra a los
   conjuntos E1/E2? ¿Algún paso usa el test antes de `05_modelo`? ¿La EDA con etiqueta usa solo `role == dev`?
2. **Partición espacial**: ¿celdas compartidas entre dev y test? ¿Pliegues por celda? Revisa `particion_resumen.json`.
3. **Cruces**: radio, elección del candidato más cercano, unidades (μ de CatWISE en arcsec/año; Gaia en mas/año),
   reglas de limpieza (`ph_qual` U, `cc_flags`, `ab_flags`) aplicadas igual a todas las clases.
4. **Fórmulas**: colores, movimiento propio reducido, C* de Riello, M_W2, flujos unWISE→magnitudes.
5. **Estadística**: BH por familia, ε², delta de Cliff, V de Cramér, supuestos de χ² (esperados ≥5).
6. **Importancia**: permutación por cluster coherente, ablación, Boruta (prueba binomial y corrección), cuota de dominancia.
7. **Robustez**: implementación del apagado de grupos; ¿la regla de elección se aplicó tal como está en `config.json`?
8. **Test**: ¿se evalúa una sola vez? ¿El umbral `desconocido` sale del OOF de desarrollo y no del test?
9. **Interpretación**: ¿`INFORME.md` afirma algo que los archivos no respaldan?
10. **Reproducibilidad**: hashes en `inventario.json`, semillas, versiones.

Formato de cada hallazgo:
```
### C-NN [ALTA|MEDIA|BAJA] título
Evidencia: ...
Riesgo: ...
Corrección propuesta: ...
```
Termina con una lista de lo que verificaste y encontraste correcto.
