#!/usr/bin/env bash
# Lanzador. Se puede relanzar: TY_PIPELINE salta lo que está al día y las descargas SPHEREx siguen donde
# quedaron. Usar dentro de tmux (ver LEEME.md).
#
#   ./ejecutar_todo.sh               todo en serie: TY 00-04 + motor 1-7
#   ./ejecutar_todo.sh --rapido      TY 00-04 + motor 4-7 sin SPHEREx (primer modelo solo con catálogo)
#   ./ejecutar_todo.sh --descargas   motor 1-3 (índice, fotometría y variables SPHEREx; necesita red)
#   ./ejecutar_todo.sh --modelos     motor 4-7 (usa SPHEREx si la etapa 3 ya terminó)
#
# --rapido y --descargas pueden correr a la vez en dos ventanas de tmux; al terminar las descargas, --modelos.
set -uo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONUTF8=1
mkdir -p logs
MODO="${1:-todo}"
LOG="logs/ejecutar_${MODO#--}_$(date +%Y%m%d_%H%M%S).log"
echo "modo: $MODO | log: $LOG"

correr_ty() {
  echo "== TY_PIPELINE 00-04 (cruce de catálogos, partición, EDA, importancia) ==" | tee -a "$LOG"
  (cd TY_PIPELINE && python -m typipe --config config/config.json \
      --stages 00_inventario 01_variables 02_particion 03_eda 04_importancia) 2>&1 | tee -a "$LOG"
}

case "$MODO" in
  todo)        correr_ty; python -m motor 2>&1 | tee -a "$LOG" ;;
  --rapido)    correr_ty; python -m motor --sin-spherex 2>&1 | tee -a "$LOG" ;;
  --descargas) python -m motor --etapas 1_indice_spherex 2_fotometria_spherex 3_features_spherex 2>&1 | tee -a "$LOG" ;;
  --modelos)   python -m motor --etapas 4_preprocesamiento 5_modelos 6_exportar 7_informe 2>&1 | tee -a "$LOG" ;;
  *) echo "modo desconocido: $MODO"; exit 2 ;;
esac
echo "== estado ==" | tee -a "$LOG"
scripts/ver_estado.sh | tee -a "$LOG"
