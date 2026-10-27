"""Saved layout toggle through real Chrome, upload, worker, index and source inspector."""

import json
from pathlib import Path

import pytest

from test.helpers.accounts import AccountRegistry
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.ingest import chunk_texts, start_parse, upload_text, wait_run
from test.helpers.uploads import sql
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import api, ok
from test.testcases.test_spa_browser import _set_viewport, _wait_testid
from test.testcases.test_spa_ingestion_browser import Scene, _assert_box_inside_image, _in_card, _press, _press_expr

pytestmark = pytest.mark.e2e


def _toggle(scene, browser, target):
    scene.files(browser)
    _wait_testid(browser, "document-more")
    _press(browser, "document-more")
    _press(browser, "document-menu-chunking")
    _wait_testid(browser, "field-layout")
    assert browser.evaluate("document.querySelector('[data-testid=\"field-layout\"]').checked") != target
    _press(browser, "field-layout")
    _press(browser, "chunk-method-submit")
    browser.wait_for("document.querySelector('[data-testid=\"chunk-method-dialog\"]') === null", "layout saved")
    _press(browser, "document-more")
    _press(browser, "document-menu-chunking")
    _wait_testid(browser, "field-layout")
    assert browser.evaluate("document.querySelector('[data-testid=\"field-layout\"]').checked") == target
    browser.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    browser.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    browser.wait_for("document.querySelector('[data-testid=\"chunk-method-dialog\"]') === null", "settings closed")


def test_layout_toggle_reparse_changes_column_order_and_keeps_source_boxes(ingress, repo_root):
    root = repo_root / "test/fixtures/phase6"
    annotation = json.loads((root / "layout-two-column.json").read_text())
    registry = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake, ChromeSession() as browser:
            _set_viewport(browser)
            owner = workspace(ingress, registry, fake, "layout")
            dataset_id = ok(create(ingress, owner))["id"]
            doc = upload_text(ingress, owner, dataset_id, (root / "layout-two-column.pdf").read_bytes(), "field-observations.pdf", mime="application/pdf")
            route = f"/api/v1/datasets/{dataset_id}/documents/{doc['id']}"
            scene = Scene(ingress, owner, fake, dataset_id)
            _toggle(scene, browser, False)
            assert ok(api(ingress, "GET", route, owner.token))["layout_recognize"] is False
            assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
            wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=120)
            text = "\n".join(b["text"] for b in chunk_texts(api, ingress, owner.token, dataset_id, doc["id"]))
            assert all(s in text for s in annotation["remove"])
            assert text.index("CHARLIE HARBOR") < text.index("BRAVO ORCHARD")
            _toggle(scene, browser, True)
            assert ok(api(ingress, "GET", route, owner.token))["layout_recognize"] is True
            assert start_parse(ingress, owner, dataset_id, [doc["id"]], confirm=True).status_code == 200
            wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=120)
            chunks = chunk_texts(api, ingress, owner.token, dataset_id, doc["id"])
            text = "\n".join(b["text"] for b in chunks)
            order = [text.index(marker) for marker in annotation["reading_order"]]
            assert order == sorted(order) and all(s not in text for s in annotation["remove"]), text
            assert {box["page"] for b in chunks for box in b["positions"]} == {1, 2}
            raw = sql("SELECT `dsl` FROM `pipeline_operation_log` WHERE `document_id`=%s ORDER BY `create_time` DESC LIMIT 1", (doc["id"],))[0][0]
            dsl = json.loads(raw) if isinstance(raw, str) else raw
            assert dsl["layout_backend"] == "deepdoc-onnx" and dsl["layout_regions"] > 0
            scene.chunks_page(browser, doc["id"])
            browser.wait_for("document.querySelectorAll('[data-testid=\"chunk-card\"]').length > 0", "layout chunks")
            _press_expr(browser, _in_card(0, "chunk-select"), "first layout chunk")
            browser.wait_for(
                "(() => {const i=document.querySelector('[data-testid=\"preview-image\"]');"
                "return i?.complete && i.naturalWidth>0 && document.querySelector('[data-testid=\"preview-box\"]') !== null;})()",
                "layout source boxes",
            )
            _assert_box_inside_image(browser)
            out = Path("output/playwright/phase6-review")
            out.mkdir(parents=True, exist_ok=True)
            browser.screenshot(str(out / "layout-columns-highlight.png"))
    finally:
        registry.cleanup()
