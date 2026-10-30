"""Saved enrichment settings, real worker/index and retrieval in actual Chrome."""
import json
from pathlib import Path
import pytest
from test.helpers.accounts import AccountRegistry
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.ingest import upload_text
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import CHAT_ID, DEFAULTS, create, workspace
from test.testcases.test_provider_flow import api, ok
from test.testcases.test_spa_browser import _set_viewport, _type_into, _wait_testid
from test.testcases.test_spa_ingestion_browser import Scene, _press
from test.testcases.test_spa_chat_browser import range_value

pytestmark = pytest.mark.e2e


def test_saved_counts_generate_retrievable_terms_without_rewriting_source(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "enrich")
            ok(api(ingress, "PATCH", DEFAULTS, owner.token, body={"chat": CHAT_ID}))
            dataset = ok(create(ingress, owner))["id"]
            source = " ".join((repo_root / "test/fixtures/phase6/enrichment-original.txt").read_text().split())
            doc = upload_text(ingress, owner, dataset, source.encode(), "enrichment-original.txt")
            fake.chat_response = json.dumps({"items":[{"index":0,"keywords":["beacon altitude"],
                                                       "questions":["How high is the east lighthouse?"]}]})
            scene = Scene(ingress, owner, fake, dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                _wait_testid(browser, "field-auto-keywords")
                _type_into(browser, "field-auto-keywords", "2")
                _type_into(browser, "field-auto-questions", "1")
                _press(browser, "chunk-method-submit")
                browser.wait_for("!document.querySelector('[data-testid=chunk-method-dialog]')", "enrichment settings saved")
                detail = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}", owner.token))
                assert detail["auto_keywords"] == 2 and detail["auto_questions"] == 1
                before = len(fake.chat_requests())
                scene.parse(doc["id"])
                assert len(fake.chat_requests()) == before + 1
                chunks = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token))
                assert chunks["total"] == 1
                item = chunks["items"][0]
                assert item["text"] == source and "beacon altitude" not in source
                assert item["generated_keywords"] == ["beacon altitude"]
                assert item["generated_questions"] == ["How high is the east lighthouse?"]
                scene.chunks_page(browser, doc["id"])
                _wait_testid(browser, "chunk-generated-keywords")
                assert "beacon altitude" in browser.evaluate("document.querySelector('[data-testid=chunk-generated-keywords]').textContent")
                assert "How high" in browser.evaluate("document.querySelector('[data-testid=chunk-generated-questions]').textContent")
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.screenshot(str(output / "enrichment-inspector.png"))
                scene.files(browser)
                _press(browser, "dataset-test-retrieval")
                _wait_testid(browser, "field-retrieval-question")
                _type_into(browser, "field-retrieval-question", "beacon altitude")
                range_value(browser, "field-retrieval-threshold", 0)
                range_value(browser, "field-retrieval-weight", 0)
                _press(browser, "retrieval-run")
                browser.wait_for("document.querySelector('[data-testid=retrieval-results]') && document.querySelector('[data-testid=retrieval-run]').getAttribute('aria-busy') !== 'true'", "retrieval finished")
                assert not browser.evaluate("Boolean(document.querySelector('[data-testid=retrieval-error]'))"), "retrieval returned an error"
                assert browser.evaluate("document.querySelectorAll('[data-testid=hit-card]').length") > 0, browser.evaluate("document.querySelector('[data-testid=retrieval-results]').textContent")
                _press(browser, "hit-source")
                browser.wait_for("document.querySelector('[data-testid=source-passage]')?.textContent.includes('52 metres')", "original passage")
                passage = browser.evaluate("document.querySelector('[data-testid=source-passage]').textContent")
                assert "73 units" in passage and "beacon altitude" not in passage
                browser.screenshot(str(output / "enrichment-retrieval.png"))
    finally:
        accounts.cleanup()
