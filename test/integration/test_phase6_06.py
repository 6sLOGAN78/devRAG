"""Actual approved native TSR/PDF on the original pre-annotated source."""

import httpx
import pytest

from test.conftest import stack_env

pytestmark = pytest.mark.integration


def test_actual_pdf_tables_keep_spans_empty_cells_page_crops_and_escaped_numbers(repo_root):
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token, "actual native service required"
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=65) as client:
        response = client.post(
            "/v1/parse",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("table.pdf", (repo_root / "test/fixtures/phase6/table-spanned-original.pdf").read_bytes())},
            data={"options": '{"layout":true}'},
        )
    assert response.status_code == 200, response.text
    tables = [block for block in response.json()["blocks"] if block.get("table")]
    assert len(tables) == 2, "actual TSR structures and owned crops are missing"
    for page, block in enumerate(tables, 1):
        table = block["table"]
        assert table["rows"] == 5 and table["columns"] == 3
        assert table["caption"] == f"Table {page}. Orchard field measurements"
        from deepdoc.geometry import iou

        bounds = block["boxes"][0]
        assert iou((bounds["x0"], bounds["top"], bounds["x1"], bounds["bottom"]), (60, 90, 540, 340)) >= 0.7
        header = next(c for c in table["cells"] if c["row"] == 0 and c["column"] == 0)
        assert header["text"] == "ORCHARD MEASUREMENTS" and header["colspan"] == 3
        empty = next(c for c in table["cells"] if c["row"] == 4 and c["column"] == 2)
        assert empty["text"] == ""
        numeric = next(c for c in table["cells"] if c["row"] == 2 and c["column"] == 1)
        assert numeric["text"] == ("9100" if page == 1 else "281")
        assert block["boxes"][0]["page"] == page
        assert len(block["assets"]) == 1 and block["assets"][0]["kind"] == "table" and block["assets"][0]["page"] == page
        assert "<b>Literal</b>" not in table["html"] and "&lt;b&gt;Literal&lt;/b&gt;" in table["html"]


def test_actual_tsr_image_endpoint_keeps_numeric_cells_and_merged_header(repo_root):
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token
    headers = {"Authorization": f"Bearer {token}"}
    source = (repo_root / "test/fixtures/phase6/table-spanned-original.pdf").read_bytes()
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=65) as client:
        page = client.post("/v1/page-image", headers=headers, files={"file": ("original.pdf", source)}, data={"options": '{"page":1,"zoom":3}'})
        assert page.status_code == 200, page.text
        result = client.post("/v1/tsr", headers=headers, files={"file": ("original-page.jpg", page.content)})
    assert result.status_code == 200, result.text
    table = result.json()["table"]
    assert table["rows"] == 5 and table["columns"] == 3
    assert table["cells"][0]["colspan"] == 3 and table["cells"][0]["text"] == "ORCHARD MEASUREMENTS"
    assert next(cell for cell in table["cells"] if cell["row"] == 2 and cell["column"] == 1)["text"] == "9100"


def test_native_table_crops_count_toward_the_total_asset_budget(repo_root):
    import base64
    import subprocess

    encoded = base64.b64encode((repo_root / "test/fixtures/phase6/table-spanned-original.pdf").read_bytes()).decode()
    code = f"""import base64
from pathlib import Path
from deepdoc.model_runtime import ModelRuntime,NativeError
from deepdoc.native_runtime import NativeRuntime
from deepdoc import pdf_service
pdf_service.MAX_ASSETS=1
runtime=NativeRuntime(ModelRuntime(Path('/models')))
try:
    runtime.process_pdf('parse',base64.b64decode({encoded!r}),{{'layout':True}})
except NativeError as error:
    if error.status!=413:raise
else:
    raise AssertionError('table crop bytes bypassed the total native asset budget')
"""
    result = subprocess.run(["docker", "exec", "-i", "devrag-stack-deepdoc-1", "/ragflow/.venv/bin/python", "-"], input=code, text=True, capture_output=True, check=False, timeout=65)
    assert result.returncode == 0, result.stderr
