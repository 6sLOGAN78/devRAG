"""Actual scanned PDF bytes enter the DeepDoc boundary and yield source geometry."""

import io
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from test.conftest import stack_env

pytestmark = pytest.mark.e2e


def test_scanned_pdf_ocr_fact_and_remote_jpeg_preview(repo_root):
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token, "real DeepDoc service is required"
    with Image.open(repo_root / "test/fixtures/phase6/ocr-planted.png") as image:
        stream = io.BytesIO()
        image.convert("RGB").save(stream, "PDF", resolution=144)
    pdf = stream.getvalue()
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url="http://127.0.0.1:9390", timeout=65) as client:
        result = client.post("/v1/parse", headers=headers, files={"file": ("scan.pdf", pdf, "application/pdf")},
                             data={"options": json.dumps({"start": 0, "end": 1, "layout": False})})
        assert result.status_code == 200
        data = result.json()
        assert "9100" in " ".join(block["text"] for block in data["blocks"])
        assert all(box["page"] == 1 for block in data["blocks"] for box in block["boxes"])
        image = client.post("/v1/page-image", headers=headers, files={"file": ("scan.pdf", pdf, "application/pdf")},
                            data={"options": '{"page":1,"zoom":3}'})
        assert image.status_code == 200 and image.headers["content-type"].startswith("image/jpeg")
        assert image.content.startswith(b"\xff\xd8")


def test_selected_scan_upload_reaches_real_worker_chunks_and_authorized_preview(ingress, repo_root):
    from test.helpers.accounts import AccountRegistry
    from test.helpers.fake_provider import running_stack_fake_provider
    from test.helpers.ingest import chunk_texts, start_parse, upload_text, wait_run
    from test.testcases.conftest import BASE_URL
    from test.testcases.test_dataset_flow import create, workspace
    from test.testcases.test_provider_flow import api, ok

    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "scan")
            outsider = accounts.register(prefix="scanother")
            dataset_id = ok(create(ingress, owner))["id"]
            with Image.open(repo_root / "test/fixtures/phase6/ocr-planted.png") as source:
                selected = source.convert("RGB")
                blank = Image.new("RGB", selected.size, "white")
                stream = io.BytesIO()
                blank.save(stream, "PDF", resolution=144, save_all=True, append_images=[selected, blank])
            doc = upload_text(ingress, owner, dataset_id, stream.getvalue(), "scan-selected.pdf", mime="application/pdf")
            route = f"/api/v1/datasets/{dataset_id}/documents/{doc['id']}"
            saved = ok(api(ingress, "PATCH", route, owner.token, body={"parser_config": {"pages": [[2, 2]]}}))
            assert saved["pages"] == [[2, 2]]
            assert ok(api(ingress, "GET", route, owner.token))["pages"] == [[2, 2]]
            _check_page_form(ingress, owner, fake, dataset_id, doc["id"])
            assert ok(api(ingress, "GET", route, owner.token))["pages"] == [[2, 2]]
            started = start_parse(ingress, owner, dataset_id, [doc["id"]])
            assert started.status_code == 200, started.text
            row = wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=120)
            assert ok(api(ingress, "GET", route, owner.token))["pages_total"] == 3
            chunks = chunk_texts(api, ingress, owner.token, dataset_id, doc["id"])
            assert chunks and row["chunk_count"] == len(chunks)
            text = " ".join(chunk["text"] for chunk in chunks)
            assert all(fact in text for fact in ("LIGHTHOUSE", "52", "ORCHARD", "9100")), text
            positions = [box for chunk in chunks for box in chunk["positions"]]
            assert positions and all(box["page"] == 2 for box in positions), positions
            assert all(0 <= box["x0"] < box["x1"] <= 700 and 0 <= box["top"] < box["bottom"] <= 200 for box in positions), positions
            preview_route = route + "/pages/2/image"
            preview = api(ingress, "GET", preview_route, owner.token)
            assert preview.status_code == 200 and preview.headers["content-type"].startswith("image/jpeg"), preview.text[:100]
            assert preview.content.startswith(b"\xff\xd8")
            _check_inspector(ingress, owner, fake, dataset_id, doc["id"])
            assert api(ingress, "GET", preview_route, outsider.token).status_code == 404
            assert api(ingress, "GET", route + "/pages/4/image", owner.token).status_code == 404
    finally:
        accounts.cleanup()


def _check_page_form(ingress, owner, fake, dataset_id, doc_id):
    from test.helpers.chrome_cdp import ChromeSession
    from test.testcases.test_spa_browser import _set_viewport, _wait_testid
    from test.testcases.test_spa_ingestion_browser import Scene, _press

    with ChromeSession() as browser:
        _set_viewport(browser)
        Scene(ingress, owner, fake, dataset_id).files(browser)
        _wait_testid(browser, "document-more")
        for value in ("2-3", "2"):
            _press(browser, "document-more")
            _press(browser, "document-menu-chunking")
            _wait_testid(browser, "field-page-ranges")
            if value == "2":
                assert browser.evaluate("document.querySelector('[data-testid=\"field-page-ranges\"]').value") == "2-3"
            browser.evaluate("(() => {const e = document.querySelector('[data-testid=\"field-page-ranges\"]');e.focus();e.select();})()")
            browser.call("Input.insertText", {"text": value})
            _press(browser, "chunk-method-submit")
            browser.wait_for("document.querySelector('[data-testid=\"chunk-method-dialog\"]') === null", "page settings saved")
        output = Path("output/playwright/phase6-review")
        output.mkdir(parents=True, exist_ok=True)
        browser.screenshot(str(output / "scan-page-selection-saved.png"))


def _check_inspector(ingress, owner, fake, dataset_id, doc_id):
    from test.helpers.chrome_cdp import ChromeSession
    from test.testcases.test_spa_browser import _set_viewport
    from test.testcases.test_spa_ingestion_browser import Scene, _assert_box_inside_image, _in_card, _press_expr

    with ChromeSession() as browser:
        _set_viewport(browser)
        Scene(ingress, owner, fake, dataset_id).chunks_page(browser, doc_id)
        browser.wait_for("document.querySelectorAll('[data-testid=\"chunk-card\"]').length > 0", "OCR chunks displayed")
        _press_expr(browser, _in_card(0, "chunk-select"), "scanned source chunk")
        browser.wait_for("(() => {const i = document.querySelector('[data-testid=\"preview-image\"]');return i?.complete && i.naturalWidth > 0;})()", "remote scan preview")
        browser.wait_for("document.querySelector('[data-testid=\"preview-box\"]') !== null", "OCR source highlight")
        assert browser.evaluate("document.querySelector('[data-testid=\"preview-caption\"]').textContent") == "Page 2 of 3"
        _assert_box_inside_image(browser)
        browser.screenshot("output/playwright/phase6-review/scan-page2-highlight.png")
