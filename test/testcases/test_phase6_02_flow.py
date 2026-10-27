"""Operator entry to the real native service, including health and boundary refusals."""

import httpx
import pytest

from test.conftest import stack_env

pytestmark = pytest.mark.e2e


def test_native_profile_health_authentication_and_corrupt_image():
    env = stack_env()
    secret = env.get("DEEPDOC_API_TOKEN", "")
    assert secret, "DeepDoc profile and operator token are required for this real flow"
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=65) as client:
        health = client.get("/health")
        assert health.status_code == 200 and health.json()["status"] == "ready"
        denied = client.post("/v1/ocr", json={"url": "http://localhost/secret"})
        assert denied.status_code == 401
        invalid = client.post("/v1/ocr", headers={"Authorization": f"Bearer {secret}"},
                              files={"file": ("bad.png", b"corrupt", "image/png")})
        assert invalid.status_code == 400 and invalid.json()["error"] == "invalid_image"
        assert secret not in invalid.text
