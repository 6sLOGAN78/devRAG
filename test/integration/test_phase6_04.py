"""Fixed original two-column PDF through actual approved ONNX runtime."""

import json

import httpx
import pytest

from test.conftest import stack_env

pytestmark = pytest.mark.integration


def test_real_layout_model_preserves_column_order_and_drops_page_furniture(repo_root):
    root = repo_root / "test/fixtures/phase6"
    annotation = json.loads((root / "layout-two-column.json").read_text())
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token, "real approved native service is required"
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=65) as client:
        response = client.post(
            "/v1/parse",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("columns.pdf", (root / "layout-two-column.pdf").read_bytes())},
            data={"options": '{"start":0,"end":1,"layout":true}'},
        )
    assert response.status_code == 200, response.text
    data = response.json()
    text = "\n".join(block["text"] for block in data["blocks"])
    indices = [text.index(marker) for marker in annotation["reading_order"]]
    assert indices == sorted(indices), text
    assert all(marker not in text for marker in annotation["remove"]), text
    assert data["report"]["layout_backend"] == "deepdoc-onnx"
    assert data["report"]["layout_regions"] > 0
    assert all(box["page"] == 1 for block in data["blocks"] for box in block["boxes"])


def test_actual_layout_endpoint_has_typed_image_regions(repo_root):
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=65) as client:
        result = client.post("/v1/layout", headers={"Authorization": f"Bearer {token}"}, files={"file": ("source.png", (repo_root / "test/fixtures/phase6/ocr-planted.png").read_bytes())})
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["schema_version"] == 1 and data["width"] == 1400 and data["height"] == 400
    assert data["regions"]
    for region in data["regions"]:
        assert 0 <= region["label_id"] <= 10 and region["score"] >= 0.08
        x0, top, x1, bottom = region["box"]
        assert 0 <= x0 < x1 <= 1400 and 0 <= top < bottom <= 400


def test_model_score_boundary_and_letterbox_round_trip_inside_native_container():
    import subprocess

    code = """from types import SimpleNamespace

import numpy as np
from PIL import Image

from deepdoc.layout import Layout

output=np.zeros((1,300,6),dtype=np.float32)
# A 512x256 image is letterboxed with 256 pixels top padding at scale 2.
output[0,0]=[20,276,220,316,0.08,0]
output[0,1]=[300,400,400,420,np.nextafter(np.float32(0.08),np.float32(0)),1]
session=SimpleNamespace(get_inputs=lambda:[SimpleNamespace(name="images")],run=lambda *_:[output])
regions=Layout(SimpleNamespace(session=lambda _:session)).detect(Image.new("RGB",(512,256)),(256,128))
assert len(regions)==1 and regions[0].label_id==2
assert regions[0].box == (5,5,55,15)
"""
    result = subprocess.run(["docker", "exec", "-i", "devrag-stack-deepdoc-1", "/ragflow/.venv/bin/python", "-"], input=code, text=True, capture_output=True, check=False, timeout=30)
    assert result.returncode == 0, result.stderr


def test_mixed_native_and_scanned_pages_share_actual_page_geometry(repo_root):
    from test.helpers.phase6_pdf import mixed_pdf

    data = mixed_pdf(repo_root / "test/fixtures/phase6/ocr-planted.png")
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=65) as client:
        response = client.post("/v1/parse", headers={"Authorization": f"Bearer {token}"}, files={"file": ("mixed.pdf", data)}, data={"options": '{"layout":true}'})
    assert response.status_code == 200, response.text
    blocks = response.json()["blocks"]
    first = " ".join(b["text"] for b in blocks if any(box["page"] == 1 for box in b["boxes"]))
    second = " ".join(b["text"] for b in blocks if any(box["page"] == 2 for box in b["boxes"]))
    assert "MIXED NATIVE FACT 73" in first
    assert "ORCHARD" in second and "9100" in second
    assert all(b["page_sizes"] in ({"1": [700.0, 200.0]}, {"2": [700.0, 200.0]}) for b in blocks)


def test_native_corrupt_text_decision_uses_actual_fixed_ratio_not_empty_only():
    import subprocess

    code = """from deepdoc.pdf_service import _valid_native_text
from rag.parsers.types import ParsedBlock
assert not _valid_native_text(None)
assert not _valid_native_text([ParsedBlock(chr(65533)*10)])
assert not _valid_native_text([ParsedBlock('A'*94+chr(65533)*6)])
assert _valid_native_text([ParsedBlock('A'*95+chr(65533)*5)])
"""
    result = subprocess.run(["docker", "exec", "-i", "devrag-stack-deepdoc-1", "/ragflow/.venv/bin/python", "-"], input=code, text=True, capture_output=True, check=False, timeout=30)
    assert result.returncode == 0, result.stderr
