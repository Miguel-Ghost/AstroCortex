"""The promoted model must satisfy the contract that Backend/app/services/classifier.py (OnnxPredictor) loads,
and Backend/models/ must hold that same model (it is what /api/sources serves)."""
import hashlib
import json
from pathlib import Path

import pytest

import main

ACTUAL = Path(main.ROOT) / "artifacts" / "models" / "actual"
BACKEND_MODELS = Path(main.ROOT).parent / "Backend" / "models"


@pytest.mark.skipif(not (ACTUAL / "model.onnx").is_file(), reason="no promoted model yet")
def test_promoted_model_contract():
    class A:
        modelo = str(ACTUAL)
    assert main.cmd_verificar(A()) == 0


@pytest.mark.skipif(not (BACKEND_MODELS / "model.onnx").is_file(), reason="Backend/ not present")
def test_backend_serves_the_promoted_model():
    sha = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (ACTUAL / "model.onnx", BACKEND_MODELS / "model.onnx")]
    versions = [json.loads((d / "metadata.json").read_text(encoding="utf-8"))["model_version"]
                for d in (ACTUAL, BACKEND_MODELS)]
    assert sha[0] == sha[1] and versions[0] == versions[1], "run: python main.py publicar"
