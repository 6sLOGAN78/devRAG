"""Original PDF table reaches real worker/index and authenticated source crop."""

import pytest
from pathlib import Path
from test.helpers.accounts import AccountRegistry
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.ingest import upload_text
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import api, ok
from test.testcases.test_spa_ingestion_browser import Scene, _press
from test.testcases.test_spa_browser import _set_viewport, _wait_testid, _type_into
from test.testcases.test_spa_chat_browser import range_value

pytestmark = pytest.mark.e2e


def test_original_spanned_tables_reach_the_product_and_owned_crop_endpoint(ingress, repo_root):
    registry = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, registry, fake, "tables")
            dataset = ok(create(ingress, owner))["id"]
            doc = upload_text(ingress, owner, dataset, (repo_root / "test/fixtures/phase6/table-spanned-original.pdf").read_bytes(), "table-original.pdf", mime="application/pdf")
            Scene(ingress, owner, fake, dataset).parse(doc["id"])
            chunks = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token))["items"]
            structures = [table for chunk in chunks for table in chunk.get("tables", [])]
            assert len(structures) == 2, "source table structures/crop associations have not reached product DTOs"
            assert {t["cells"][0]["colspan"] for t in structures} == {3}
            assert all(set(table) == {"rows", "columns", "cells", "caption", "asset_id"} for table in structures)
            assert "asset_sha256" not in str(chunks) and "object_key" not in str(chunks)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene = Scene(ingress, owner, fake, dataset)
                scene.files(browser)
                _press(browser, "dataset-test-retrieval")
                _wait_testid(browser, "field-retrieval-question")
                _type_into(browser, "field-retrieval-question", "Harvest 9100")
                range_value(browser, "field-retrieval-threshold", 0)
                range_value(browser, "field-retrieval-weight", 0)
                _press(browser, "retrieval-run")
                _wait_testid(browser, "hit-card")
                _press(browser, "hit-source")
                browser.wait_for("document.querySelectorAll('[data-testid=\"source-structured-table\"]').length===2", "both original page tables")
                assert browser.evaluate("document.querySelector('[data-testid=\"source-structured-table\"] th').colSpan") == 3
                assert browser.evaluate("document.querySelectorAll('[data-testid=\"source-structured-table\"] b').length") == 0
                assert browser.evaluate("[...document.querySelectorAll('[data-testid=\"source-structured-table\"] td')].some(e=>e.textContent==='')")
                browser.wait_for(
                    "(() => { const images=[...document.querySelectorAll('[data-testid=\"source-asset-image\"]')];return images.length===2 && images.every(i=>i.complete && i.naturalWidth>100 && i.src.startsWith('blob:'));})()",
                    "authenticated table crops",
                )
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.screenshot(str(output / "structured-table-and-crop.png"))
            for table in structures:
                image = api(ingress, "GET", "/api/v1/documents/images/" + table["asset_id"], owner.token)
                assert image.status_code == 200 and image.content.startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        registry.cleanup()
