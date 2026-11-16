#!/usr/bin/env bash
# Instala el entorno en la máquina Vast (Ubuntu). Una sola vez. Crea .venv con Python 3.13.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
exec > >(tee -a logs/instalar.log) 2>&1

echo "== $(date -u +%FT%TZ) instalación =="
if ! command -v tmux >/dev/null 2>&1 || ! command -v unzip >/dev/null 2>&1 || ! command -v zip >/dev/null 2>&1; then
  (apt-get update -y && apt-get install -y tmux unzip zip) || echo "AVISO: no se pudo instalar tmux/zip con apt"
fi
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv venv --python 3.13 .venv
# shellcheck disable=SC1091
source .venv/bin/activate
uv pip install -r requirements.txt
# torch: rueda CPU (la red es tabular y chica; la GPU no hace falta). Si el índice CPU falla, se usa PyPI.
uv pip install "torch==2.15.0" --index-url https://download.pytorch.org/whl/cpu || uv pip install "torch==2.15.0"
python -m ipykernel install --user --name clasificador --display-name "Clasificador (.venv)" || true
echo "== prueba sin red de las etapas SPHEREx =="
python tests/prueba_spherex_sintetica.py | tail -1
echo "== conexión con IRSA y S3 =="
python tests/verificar_red.py
echo "== instalación terminada =="
