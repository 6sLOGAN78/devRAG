"""Member saves Table, uploads a workbook and retrieves a row citation through Chrome."""

from pathlib import Path
import json
import pytest
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


def test_saved_table_choice_and_retrieved_row_context(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "table")
            dataset = ok(create(ingress, owner))["id"]
            path = repo_root / "test/fixtures/phase6/table-original.xlsx"
            gold = json.loads(path.with_name("table-original-annotation.json").read_text())
            doc = upload_text(ingress, owner, dataset, path.read_bytes(), path.name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            scene = Scene(ingress, owner, fake, dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                _wait_testid(browser, "chunk-method-option-table")
                _press(browser, "chunk-method-option-table")
                _press(browser, "chunk-method-submit")
                browser.wait_for("!document.querySelector('[data-testid=\"chunk-method-dialog\"]')", "Table choice saved")
                detail = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}", owner.token))
                assert detail["parser_id"] == "table"
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                _wait_testid(browser, "chunk-method-option-table")
                assert browser.evaluate("document.querySelector('[data-testid=\"chunk-method-option-table\"]').checked") is True
                browser.evaluate('document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}))')
                scene.parse(doc["id"])
                chunks = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token))
                assert chunks["total"] == 2
                assert "Lighthouse" in chunks["items"][0]["text"]
                assert all(c["positions"] == [] for c in chunks["items"])
                scene.files(browser)
                _press(browser, "dataset-test-retrieval")
                _wait_testid(browser, "field-retrieval-question")
                _type_into(browser, "field-retrieval-question", "Lighthouse Height metres calibration73")
                range_value(browser, "field-retrieval-threshold", 0)
                range_value(browser, "field-retrieval-weight", 0)
                _press(browser, "retrieval-run")
                _wait_testid(browser, "hit-card")
                _press(browser, "hit-source")
                browser.wait_for('document.querySelector(\'[data-testid="source-passage"]\')?.textContent.includes("calibration73")', "row citation")
                passage = browser.evaluate("document.querySelector('[data-testid=\"source-passage\"]').textContent")
                assert "Height metres: 52" in passage and "Site measurements" in passage
                assert "orchard9100" not in passage and "Orchard" not in passage
                assert browser.evaluate('document.querySelectorAll(\'[data-testid="source-passage"] img, [data-testid="source-passage"] script\').length') == 0
                browser.wait_for('document.querySelector(\'[data-testid="source-drawer"]\').getAnimations({subtree:true}).every(a=>a.playState!=="running")', "source motion settled")
                _wait_testid(browser, "source-structured-table")
                assert browser.evaluate("document.querySelector('[data-testid=\"source-structured-table\"]').textContent").find("52") >= 0
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.screenshot(str(output / "table-row-context.png"))
    finally:
        accounts.cleanup()
