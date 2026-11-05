"""Real DeepDoc byte route and operator-availability boundary for optional PDF services.

These checks never submit to an external provider. One real Docling and MinerU parse
belongs to the separately budgeted live gate when endpoints are configured.
"""

import json
import subprocess

import httpx
import pytest

from test.conftest import stack_env
from test.helpers.pdf_files import text_pdf

pytestmark = pytest.mark.integration


def test_real_deepdoc_route_authenticates_and_refuses_unconfigured_selected_backends():
    values = stack_env()
    token = values.get("DEEPDOC_API_TOKEN")
    assert token, "real DeepDoc operator token is required"
    project = values.get("COMPOSE_PROJECT_NAME", "devrag-stack")
    inspected = subprocess.run(
        ["docker", "inspect", "--format", "{{json .Config.Env}}", f"{project}-deepdoc-1"],
        capture_output=True, text=True, check=False, timeout=10,
    )
    assert inspected.returncode == 0, "running DeepDoc container configuration is required"
    runtime = dict(pair.split("=", 1) for pair in json.loads(inspected.stdout) if "=" in pair)
    content = text_pdf([["Lighthouse 52", "Owner 73"]])
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=15, trust_env=False) as client:
        assert client.get("/health").status_code == 200
        for name in ("docling", "mineru"):
            options = {"backend": name, "layout": True, "max_pages": 1, "max_text_bytes": 4096}
            files = {"file": ("source.pdf", content, "application/pdf")}
            denied = client.post("/v1/parse", files=files, data={"options": json.dumps(options)})
            assert denied.status_code == 401
            if not runtime.get(f"PDF_BACKEND_{name.upper()}_URL"):
                unavailable = client.post("/v1/parse", files=files, data={"options": json.dumps(options)},
                                          headers={"Authorization": "Bearer " + token})
                assert unavailable.status_code == 503
                assert unavailable.json() == {"schema_version": 1, "error": "backend_unavailable"}
