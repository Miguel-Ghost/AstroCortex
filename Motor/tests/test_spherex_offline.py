"""End-to-end test of the SPHEREx stages 1-3 with synthetic MEF files (no network).

Runs the script in its own process: its photometry thread pool stalls under pytest's output capture.
"""
import subprocess
import sys
from pathlib import Path


def test_synthetic_index_photometry_features():
    script = Path(__file__).with_name("prueba_spherex_sintetica.py")
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=600,
                       cwd=script.parents[1])
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "RESULTADO: OK" in r.stdout
