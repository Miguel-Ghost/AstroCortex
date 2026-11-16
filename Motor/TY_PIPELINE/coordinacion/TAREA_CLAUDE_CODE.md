# Tarea para Claude Code: ejecutor local del clasificador T/Y

Directorio: `C:/Users/Paolo/Downloads/NASA SPACE APPS/CLASIFICADOR_TY/TY_PIPELINE`.
Lee `coordinacion/PROTOCOLO.md` y `README.md`. Respeta `NASA SPACE APPS/CLAUDE.md`.

1. Trabaja en la rama `claude/clasificador-ty` (créala desde la rama actual si no existe). Sin push ni merge.
2. Ejecuta `./ejecutar.sh` (o `windows/01_instalar_entorno.bat` y luego `windows/02_ejecutar_pipeline.bat`).
3. Lee `../resultados_TY/run_001/ESTADO.json`.
   - Si una etapa falló por entorno, ruta, dependencia o compatibilidad de versión, corrige lo mínimo,
     vuelve a ejecutar (reanuda solo) y documenta en `coordinacion/BITACORA.md`: error, causa, cambio, resultado.
   - Si el fallo exige cambiar reglas científicas (variables prohibidas, partición, umbrales, regla de
     elección), NO lo cambies: descríbelo en `BITACORA.md` y detente.
4. Cuando `resumen.global` sea `COMPLETO`, haz commit solo de `TY_PIPELINE` (código, config, docs,
   coordinación; sin `.venv`, `logs` ni resultados) con un mensaje descriptivo.
5. Escribe al final de `BITACORA.md`: estado final, duración por etapa y las advertencias de `ESTADO.json`.
