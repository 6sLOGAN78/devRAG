"""A member batch-edits metadata and reads its flattened/config views in actual Chrome."""
from pathlib import Path

import pytest

from test.helpers.accounts import AccountRegistry
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.ingest import upload_text
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import api, ok
from test.testcases.test_spa_browser import _set_viewport, _type_into
from test.testcases.test_spa_ingestion_browser import Scene, _press

pytestmark = pytest.mark.e2e


def test_original_metadata_edit_flatten_config_and_source(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "metadata")
            dataset = ok(create(ingress, owner))["id"]
            path = repo_root / "test/fixtures/phase6/tags-original.txt"
            document = upload_text(ingress, owner, dataset, path.read_bytes(), path.name)
            doc_id = document["id"]
            scene = Scene(ingress, owner, fake, dataset)
            scene.parse(doc_id)
            chunks_before = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc_id}/chunks", owner.token))
            assert chunks_before["total"] == 1
            source_before = chunks_before["items"][0]
            assert "52 metres" in source_before["text"] and "73 units" in source_before["text"]
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "document-select")
                _press(browser, "selection-metadata")
                browser.wait_for("document.querySelector('[data-testid=metadata-config]')?.textContent.includes('Automatic metadata off')", "metadata configuration")
                _type_into(browser, "metadata-key", "height_metres")
                browser.evaluate("const item=document.querySelector('[data-testid=metadata-type]');item.value='number';item.dispatchEvent(new Event('change',{bubbles:true}))")
                _type_into(browser, "metadata-value", "52")
                _press(browser, "metadata-save")
                browser.wait_for("document.querySelector('[data-testid=dataset-metadata-section]')?.textContent.includes('height_metres')", "flattened metadata")
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.screenshot(str(output / "metadata-manager.png"))
            detail = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc_id}", owner.token))
            assert detail["metadata"] == {"height_metres": 52}
            flattened = ok(api(ingress, "GET", f"/api/v1/datasets/metadata/flattened?dataset_ids={dataset}", owner.token))
            assert flattened == {"fields": [{"name": "height_metres", "type": "number", "total": 1, "values": [52]}], "page": 1, "page_size": 100, "has_more": False}
            assert ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/metadata/config", owner.token)) == {"enabled": False, "schema": [], "model_id": ""}
            chunks_after = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc_id}/chunks", owner.token))
            assert chunks_after["items"][0]["text"] == source_before["text"]
            assert chunks_after["items"][0].get("positions") == source_before.get("positions")
    finally:
        accounts.cleanup()
