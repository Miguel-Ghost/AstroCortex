#!/usr/bin/env bash
# Junta lo que hay que devolver al equipo en un zip (sin cachés de descarga ni el entorno).
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="ENTREGA_CLASIFICADOR_$(date +%Y%m%d_%H%M).zip"
zip -qr "$OUT" salidas resultados_TY/run_004 logs config \
  -x "salidas/1_indice_spherex/cache/*" "salidas/2_fotometria_spherex/partes/*" "*.tmp"
ls -lh "$OUT"
echo "Copiar a la PC:  scp -P <PUERTO> root@<IP>:$(pwd)/$OUT ."
