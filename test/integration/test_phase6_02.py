"""Real provisioned OCR service: selected integration requires its actual running container."""

import io
import subprocess

import httpx
import pytest

from test.conftest import stack_env

pytestmark = pytest.mark.integration


def test_real_ocr_returns_fixed_planted_facts_and_image_bounds(repo_root):
    env = stack_env()
    secret = env.get("DEEPDOC_API_TOKEN", "")
    assert secret, "Provision the approved DeepDoc operator token before native integration"
    image = (repo_root / "test/fixtures/phase6/ocr-planted.png").read_bytes()
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=65) as client:
        result = client.post("/v1/ocr", headers={"Authorization": f"Bearer {secret}"},
                             files={"file": ("page.png", io.BytesIO(image), "image/png")})
    assert result.status_code == 200
    data = result.json()
    text = " ".join(span["text"] for span in data["spans"]).upper()
    assert "52" in text and "9100" in text
    assert "LIGHTHOUSE" in text and "ORCHARD" in text
    assert (data["width"], data["height"]) == (1400, 400)
    for span in data["spans"]:
        x0, y0, x1, y1 = span["box"]
        assert 0 <= x0 < x1 <= 1400 and 0 <= y0 < y1 <= 400
        assert 0 <= span["confidence"] <= 1


def test_cold_native_runtime_refuses_missing_models_without_network():
    result = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "--read-only", "--memory", "512m", "--cpus", "2",
         "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
         "--env", "DEEPDOC_API_TOKEN=test-only-native-startup-token-0001",
         "--env", "DEEPDOC_MODEL_DIR=/absent-models", "devrag-deepdoc:local"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode != 0 and "model_unavailable" in result.stderr
    assert "Running on" not in result.stderr
