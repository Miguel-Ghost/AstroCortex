"""Prueba de punta a punta con datos SINTÉTICOS en una carpeta temporal.
Uso: python tests/run_synthetic_test.py   (sale con código 0 si las 8 etapas terminan)."""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import make_synthetic  # noqa: E402
from typipe.__main__ import main  # noqa: E402

root = Path(tempfile.mkdtemp(prefix="typipe_sintetico_"))
data, out = root / "datos", root / "salida"
make_synthetic.main(data)
cfg = json.loads((HERE.parent / "config" / "config.json").read_text(encoding="utf-8"))
d = str(data).replace("\\", "/")
cfg["paths"] = {"input_root": d, "processed": d + "/data/processed",
                "ultracoolsheet": d + "/data/raw/ultracoolsheet/UltracoolSheet_-_Main.csv",
                "noirlab_catalogs": d + "/CLASIFICADOR_TY/data/catalogos_noirlab",
                "spherex_index": d + "/CLASIFICADOR_TY/data/spherex_index/pilot_image_index.jsonl",
                "spherex_raw": d + "/CLASIFICADOR_TY/data/spherex_raw_mef",
                "fits_status": d + "/logs/run_2.status", "output_root": str(out).replace("\\", "/")}
cfg["run_id"] = "prueba_sintetica"
cfg["importance"].update({"boruta_iterations": 8, "permutation_repeats": 2})
cfg_path = root / "config_sintetico.json"
cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
code = main(["--config", str(cfg_path)])
print("salida en", out, "| código", code)
sys.exit(code)
