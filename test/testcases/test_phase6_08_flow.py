"""Saved Manual choice and original code/table source in a real browser."""

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


def test_original_manual_saved_choice_and_safe_source_code_table(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "manual")
            dataset = ok(create(ingress, owner))["id"]
            path = repo_root / "test/fixtures/phase6/manual-original.md"
            doc = upload_text(ingress, owner, dataset, path.read_bytes(), "manual-original.md", mime="text/markdown")
            scene = Scene(ingress, owner, fake, dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                _wait_testid(browser, "chunk-method-option-manual")
                _press(browser, "chunk-method-option-manual")
                _press(browser, "chunk-method-submit")
                browser.wait_for("!document.querySelector('[data-testid=\"chunk-method-dialog\"]')", "Manual choice saved")
                detail = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}", owner.token))
                assert detail["parser_id"] == "manual"
                scene.parse(doc["id"])
                rows = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token))
                assert rows["total"] == 2
                code = "````python\n" + path.read_text().split("````python\n", 1)[1].split("\n````", 1)[0] + "\n````\n"
                assert any(code in c["text"] for c in rows["items"])
                scene.files(browser)
                _press(browser, "dataset-test-retrieval")
                _wait_testid(browser, "field-retrieval-question")
                _type_into(browser, "field-retrieval-question", "LIGHTHOUSE tower 52 ORCHARD harvest 9100")
                range_value(browser, "field-retrieval-threshold", 0)
                range_value(browser, "field-retrieval-weight", 0)
                _press(browser, "retrieval-run")
                _wait_testid(browser, "hit-card")
                _press(browser, "hit-source")
                try:
                    browser.wait_for(
                        "Boolean(document.querySelector('[data-testid=\"source-passage\"] pre code') && document.querySelector('[data-testid=\"source-passage\"] table'))",
                        "original code and parameter table",
                    )
                except TimeoutError:
                    browser.screenshot("ragflow-logs/phase6-08-source-failure.png")
                    diagnostic = browser.evaluate(
                        "({name:document.querySelector('[data-testid=\"source-document\"]')?.textContent,passage:document.querySelector('[data-testid=\"source-passage\"]')?.innerHTML})"
                    )
                    Path("ragflow-logs/phase6-08-source-failure.json").write_text(json.dumps(diagnostic))
                    raise
                assert browser.evaluate("document.querySelector('[data-testid=\"source-passage\"] pre code').textContent") == code.split("\n", 1)[1].rsplit("````\n", 1)[0]
                assert browser.evaluate('document.querySelectorAll(\'[data-testid="source-passage"] img, [data-testid="source-passage"] script\').length') == 0
                assert browser.evaluate("window.manualExecuted===undefined")
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.wait_for(
                    "(() => { const e=document.querySelector('[data-testid=\"source-drawer\"]'); if(!e)return false; const r=e.getBoundingClientRect(); return r.left>=0 && r.right<=innerWidth+1 && e.getAnimations({subtree:true}).every(a=>a.playState!=='running'); })()",
                    "source drawer animation and viewport bounds",
                )
                browser.screenshot(str(output / "markdown-manual-source.png"))
                _press(browser, "source-close")
                browser.wait_for("!document.querySelector('[data-testid=\"source-drawer\"]')", "first source closed")
                browser.evaluate("document.querySelectorAll('[data-testid=\"hit-source\"]')[1].click()")
                browser.wait_for("document.querySelector('[data-testid=\"source-passage\"]')?.textContent.includes('CALIBRATION FACT: offset 73 units.')", "separate calibration source")
                assert browser.evaluate('document.querySelectorAll(\'[data-testid="source-passage"] img, [data-testid="source-passage"] script\').length') == 0
                assert browser.evaluate("window.manualExecuted===undefined")
    finally:
        accounts.cleanup()
