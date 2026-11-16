# Protocolo de trabajo: Claude (control) + Claude Code (ejecutor) + Codex (auditor)

Coherente con `NASA SPACE APPS/CLAUDE.md` y `AGENTS.md`.

## Roles

| Agente | Rol | Puede | No puede |
|---|---|---|---|
| Claude (chat, control) | decide plan, acepta o rechaza cambios y hallazgos | escribir el código de `TY_PIPELINE`, fijar reglas en `config.json` | — |
| Claude Code (Git Bash) | ejecutor local | correr instalador y pipeline, arreglar errores de entorno, commits en `claude/clasificador-ty` | cambiar reglas científicas, umbrales o la partición; push/merge |
| Codex (Git Bash) | auditor independiente | leer código y resultados, escribir `AUDITORIA_CODEX.md` en su rama `audit/clasificador-ty` | modificar `typipe/`, `config/` o resultados |

## Ciclo

1. Claude Code ejecuta `./ejecutar.sh` y deja `resultados_TY/run_001/ESTADO.json`.
2. Si una etapa falla por entorno o rutas, Claude Code lo arregla y lo explica en `coordinacion/BITACORA.md`.
   Si falla por diseño científico, se detiene y lo anota allí.
3. Codex audita con `coordinacion/TAREA_CODEX_AUDITORIA.md` y escribe hallazgos numerados (C-01, C-02…).
4. Claude revisa cada hallazgo: ACEPTADO (se corrige), RECHAZADO (con motivo) o PENDIENTE.
   Tras 3 rondas de desacuerdo decide Paolo.
5. Un hallazgo se cierra solo después de que Codex vea la corrección.

## Reglas comunes

- Entradas en `SpaceApps2026_Reto`: solo lectura. FITS originales inmutables.
- Nada de push, merge, borrado ni instalación fuera de `TY_PIPELINE/.venv`.
- Texto en UTF-8, escrito desde Python o desde el editor; no usar `Out-File`/`Set-Content`.
- Estados honestos: `NOT_RUN_*`, `DEGRADED`, `STATE_UNVERIFIED`. No afirmar resultados no ejecutados.
- Prohibido "mejorar" métricas cambiando la partición, el umbral o las variables después de ver el test.
