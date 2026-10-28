"""Saved Q&A choice and multiline answers from actual quoted CSV/JSON."""

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


def test_saved_qa_choice_and_retrieval_keep_quoted_multiline_answer(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "qa")
            dataset = ok(create(ingress, owner))["id"]
            root = repo_root / "test/fixtures/phase6"
            gold = json.loads((root / "qa-original-annotation.json").read_text())
            doc = upload_text(ingress, owner, dataset, (root / "qa-original.csv").read_bytes(), "qa-original.csv", mime="text/csv")
            scene = Scene(ingress, owner, fake, dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                _wait_testid(browser, "chunk-method-option-qa")
                _press(browser, "chunk-method-option-qa")
                _press(browser, "chunk-method-submit")
                browser.wait_for("!document.querySelector('[data-testid=\"chunk-method-dialog\"]')", "Q&A choice saved")
                detail = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}", owner.token))
                assert detail["parser_id"] == "qa"
                scene.parse(doc["id"])
                rows = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token))
                assert rows["total"] == 2 and any(gold["answers"][0] in r["text"] for r in rows["items"])
                other = upload_text(ingress, owner, dataset, (root / "qa-original.json").read_bytes(), "qa-original.json", mime="application/json")
                ok(api(ingress, "PATCH", f"/api/v1/datasets/{dataset}/documents/{other['id']}", owner.token, body={"parser_id": "qa"}))
                scene.parse(other["id"])
                scene.files(browser)
                _press(browser, "dataset-test-retrieval")
                _wait_testid(browser, "field-retrieval-question")
                _type_into(browser, "field-retrieval-question", gold["questions"][0])
                range_value(browser, "field-retrieval-threshold", 0)
                range_value(browser, "field-retrieval-weight", 0)
                _press(browser, "retrieval-run")
                _wait_testid(browser, "hit-card")
                _press(browser, "hit-source")
                browser.wait_for("document.querySelector('[data-testid=\"source-passage\"]')?.textContent.includes('52 metres.')", "paired lighthouse answer")
                passage = browser.evaluate("document.querySelector('[data-testid=\"source-passage\"]').textContent")
                assert gold["answers"][0] in passage and "9100 kilograms." not in passage
                assert browser.evaluate('document.querySelectorAll(\'[data-testid="source-passage"] img, [data-testid="source-passage"] script\').length') == 0
                browser.wait_for("document.querySelector('[data-testid=\"source-drawer\"]').getAnimations({subtree:true}).every(a=>a.playState!=='running')", "source motion settled")
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.screenshot(str(output / "qa-multiline-source.png"))
    finally:
        accounts.cleanup()
