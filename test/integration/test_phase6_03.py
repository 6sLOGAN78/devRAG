"""Real remote PDF processing through the isolated native service."""

import httpx
import pytest

from test.conftest import stack_env
from test.helpers.pdf_files import text_pdf

pytestmark = pytest.mark.integration


def test_remote_pdf_counts_and_selected_pages_preserve_native_text():
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token, "real DeepDoc service is required"
    pdf = text_pdf([["FIRST NATIVE FACT 73"], ["SECOND NATIVE FACT 91"], ["THIRD NATIVE FACT 27"]])
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=65) as client:
        headers = {"Authorization": f"Bearer {token}"}
        info = client.post("/v1/document/info", headers=headers, files={"file": ("doc.pdf", pdf, "application/pdf")})
        assert info.status_code == 200 and info.json()["pages_total"] == 3
        parsed = client.post("/v1/parse", headers=headers, files={"file": ("doc.pdf", pdf, "application/pdf")},
                             data={"options": '{"start":1,"end":2,"layout":false}'})
    assert parsed.status_code == 200
    data = parsed.json()
    assert data["report"]["pages_total"] == 1
    assert "SECOND NATIVE FACT 91" in " ".join(block["text"] for block in data["blocks"])
    assert all(box["page"] == 2 for block in data["blocks"] for box in block["boxes"])


@pytest.mark.parametrize("options", [{"rotations": {0: 90}}, {"rotations": {0: 270}}, {"cropbox": (50, 200, 500, 842)}])
def test_remote_geometry_matches_actual_rotated_or_cropped_page_ink(options):
    import io
    from types import SimpleNamespace

    from PIL import Image

    from test.unit_test.test_pdf_parser import _ink

    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token, "real DeepDoc service is required"
    pdf = text_pdf([["Alignment check line"]], **options)
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=65) as client:
        result = client.post("/v1/parse", headers=headers, files={"file": ("source.pdf", pdf)}, data={"options": '{"layout":false}'})
        assert result.status_code == 200
        block = result.json()["blocks"][0]
        preview = client.post("/v1/page-image", headers=headers, files={"file": ("source.pdf", pdf)}, data={"options": '{"page":1,"zoom":3}'})
        assert preview.status_code == 200
    with Image.open(io.BytesIO(preview.content)) as image:
        assert _ink(image, SimpleNamespace(**block["boxes"][0]), block["page_sizes"]["1"]) >= 0.02


def test_layout_request_reaches_the_real_backend_after_plan04_activation():
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token, "real DeepDoc service is required"
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=65) as client:
        result = client.post("/v1/parse", headers={"Authorization": f"Bearer {token}"},
                             files={"file": ("source.pdf", text_pdf([["NATIVE FACT"]]))},
                             data={"options": '{"layout":true}'})
    assert result.status_code == 200
    assert result.json()["report"]["layout_backend"] == "deepdoc-onnx"
    assert "NATIVE FACT" in " ".join(b["text"] for b in result.json()["blocks"])
