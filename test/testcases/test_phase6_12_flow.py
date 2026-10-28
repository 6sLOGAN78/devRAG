"""Member saves Laws, uploads legal article and retrieves an article citation through Chrome."""

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


def test_saved_laws_choice_and_retrieved_article_ancestry(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "laws")
            dataset = ok(create(ingress, owner))["id"]
            path = repo_root / "test/fixtures/phase6/laws-original.txt"
            gold = json.loads(path.with_name("laws-original-annotation.json").read_text())
            doc = upload_text(ingress, owner, dataset, path.read_bytes(), path.name, mime="text/plain")
            scene = Scene(ingress, owner, fake, dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                _wait_testid(browser, "chunk-method-option-laws")
                _press(browser, "chunk-method-option-laws")
                _press(browser, "chunk-method-submit")
                browser.wait_for("!document.querySelector('[data-testid=\"chunk-method-dialog\"]')", "Laws choice saved")
                detail = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}", owner.token))
                assert detail["parser_id"] == "laws"
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                _wait_testid(browser, "chunk-method-option-laws")
                assert browser.evaluate("document.querySelector('[data-testid=\"chunk-method-option-laws\"]').checked") is True
                browser.evaluate('document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}))')
                scene.parse(doc["id"])
                chunks = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token))
                assert chunks["total"] == 3
                assert gold["facts"][0] in chunks["items"][0]["text"] and gold["facts"][1] in chunks["items"][1]["text"]
                scene.files(browser)
                _press(browser, "dataset-test-retrieval")
                _wait_testid(browser, "field-retrieval-question")
                range_value(browser, "field-retrieval-threshold", 0)
                range_value(browser, "field-retrieval-weight", 0)
                passages = []
                for query in ["檔案保存期限", "档案保存期限"]:
                    if passages:
                        _press(browser, "source-close")
                        browser.wait_for("!document.querySelector('[data-testid=\"source-drawer\"]')", "previous source closed")
                    browser.evaluate("document.querySelector('[data-testid=\"field-retrieval-question\"]').select()")
                    _type_into(browser, "field-retrieval-question", query)
                    assert browser.evaluate("document.querySelector('[data-testid=\"field-retrieval-question\"]').value") == query
                    if passages:
                        browser.wait_for("Boolean(document.querySelector('[data-testid=\"retrieval-stale\"]'))", "changed query committed")
                    _press(browser, "retrieval-run")
                    browser.wait_for(
                        "!document.querySelector('[data-testid=\"retrieval-stale\"]') && document.querySelector('[data-testid=\"retrieval-run\"]')?.getAttribute('aria-busy') !== 'true' && Boolean(document.querySelector('[data-testid=\"hit-card\"]'))",
                        "new query results ready",
                    )
                    _press(browser, "hit-source")
                    browser.wait_for('document.querySelector(\'[data-testid="source-passage"]\')?.textContent.includes("七十三年")', "original legal citation")
                    passage = browser.evaluate("document.querySelector('[data-testid=\"source-passage\"]').textContent")
                    assert "檔案保存期限為七十三年" in passage and "第一章 檔案管理" in passage
                    assert "档案" not in passage and "L9100" not in passage
                    assert browser.evaluate("document.querySelector('[data-testid=\"field-retrieval-question\"]').value") == query
                    assert any(r.path.endswith("/embeddings") and r.body.get("input") in (query, [query]) for r in fake.requests)
                    passages.append(passage)
                    browser.wait_for('document.querySelector(\'[data-testid="source-drawer"]\').getAnimations({subtree:true}).every(a=>a.playState!=="running")', "source motion settled")
                    output = Path("output/playwright/phase6-review")
                    output.mkdir(parents=True, exist_ok=True)
                    browser.screenshot(str(output / "laws-original-source.png"))
                assert passages[0] == passages[1]
    finally:
        accounts.cleanup()
