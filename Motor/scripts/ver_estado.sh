#!/usr/bin/env bash
# Resumen corto del avance de TY_PIPELINE (run_004) y del motor. No modifica nada.
cd "$(dirname "$0")/.."
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
"$PY" - <<'EOF'
import json, pathlib
for name, p, key, st in (("TY_PIPELINE run_004", "resultados_TY/run_004/ESTADO.json", "stages", "status"),
                         ("motor", "salidas/ESTADO.json", "etapas", "estado")):
    f = pathlib.Path(p)
    if not f.is_file():
        print(f"{name}: sin iniciar"); continue
    d = json.loads(f.read_text(encoding="utf-8"))
    print(f"{name}: {d.get('resumen')}")
    for k, v in d[key].items():
        extra = v.get("error") or v.get("motivo") or ""
        print(f"   {k:24s} {v.get(st):18s} {str(v.get('seconds', v.get('segundos', '')))[:8]:>8}  {extra[:120]}")
EOF
for f in salidas/1_indice_spherex/resumen.json salidas/2_fotometria_spherex/resumen.json; do
  [ -f "$f" ] && echo "-- $f" && head -c 600 "$f" && echo
done
tail -n 3 salidas/motor.log 2>/dev/null
