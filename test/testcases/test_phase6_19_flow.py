"""A member saves Tag, parses the original source, sees its features and manages them in Chrome."""
from pathlib import Path

import pytest

from test.helpers.accounts import AccountRegistry
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.ingest import upload_text
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import api, ok
from test.testcases.test_spa_browser import _set_viewport, _type_into, _wait_testid
from test.testcases.test_spa_ingestion_browser import Scene, _press
from test.testcases.test_spa_chat_browser import range_value

pytestmark = pytest.mark.e2e


def test_tag_rank_list_aggregation_delete_and_original_retrieval(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "tag")
            dataset = ok(create(ingress, owner))["id"]
            path = repo_root / "test/fixtures/phase6/tags-original.txt"
            doc = upload_text(ingress, owner, dataset, path.read_bytes(), path.name)
            scene = Scene(ingress, owner, fake, dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                _press(browser, "chunk-method-option-tag")
                _wait_testid(browser, "tag-settings-note")
                assert browser.evaluate("document.querySelector('[data-testid=field-overlap]').disabled")
                _press(browser, "chunk-method-submit")
                browser.wait_for("!document.querySelector('[data-testid=chunk-method-dialog]')", "Tag choice saved")
                detail = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}", owner.token))
                assert detail["parser_id"] == "tag"
                scene.parse(doc["id"])
                chunks = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token))
                assert chunks["total"] == 1
                assert "52 metres" in chunks["items"][0]["text"] and "73 units" in chunks["items"][0]["text"]

                scene.files(browser)
                _press(browser, "dataset-tags-open")
                browser.wait_for("document.querySelector('[data-testid=dataset-tags-section]')?.textContent.includes('lighthouse')", "weighted source tags")
                tags = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/tags", owner.token))
                values = {item["tag"]: item for item in tags["items"]}
                assert values["lighthouse"]["count"] == values["calibration"]["count"] == 1
                assert values["lighthouse"]["weight"] / values["calibration"]["weight"] == pytest.approx(4 / 5)

                browser.evaluate("document.querySelector('[data-testid=dataset-pagerank]').select()")
                _type_into(browser, "dataset-pagerank", "2")
                assert browser.evaluate("document.querySelector('[data-testid=dataset-pagerank]').value") == "2"
                assert not browser.evaluate("document.querySelector('[data-testid=dataset-pagerank-save]').disabled")
                _press(browser, "dataset-pagerank-save")
                browser.wait_for("document.body.textContent.includes('PageRank saved')", "PageRank saved")
                saved = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}", owner.token))
                assert saved["pagerank"] == 2

                _press(browser, "tags-aggregation-open")
                _press(browser, "tags-aggregate")
                browser.wait_for("document.querySelector('[data-testid=tags-aggregate-result]')?.textContent.includes('lighthouse')", "selection-scoped aggregation")
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.screenshot(str(output / "tag-manager.png"))
                aggregate = ok(api(ingress, "GET", f"/api/v1/datasets/tags/aggregation?dataset_ids={dataset}", owner.token))
                assert {item["tag"] for item in aggregate["items"]} == set(values)

                _press(browser, "dataset-test-retrieval")
                _wait_testid(browser, "field-retrieval-question")
                _type_into(browser, "field-retrieval-question", "lighthouse height 52 metres calibration offset 73 units")
                range_value(browser, "field-retrieval-threshold", 0)
                range_value(browser, "field-retrieval-weight", 0)
                _press(browser, "retrieval-run")
                _wait_testid(browser, "hit-card")
                _press(browser, "hit-source")
                browser.wait_for("document.querySelector('[data-testid=source-passage]')?.textContent.includes('52 metres')", "original Tag source")
                assert "73 units" in browser.evaluate("document.querySelector('[data-testid=source-passage]').textContent")
                browser.screenshot(str(output / "tag-rank-source.png"))

                scene.files(browser)
                _press(browser, "dataset-tags-open")
                browser.wait_for("document.querySelector('[data-testid=dataset-tags-section]')?.textContent.includes('calibration')", "tags reloaded")
                browser.evaluate("document.querySelector('input[aria-label=calibration]').click()")
                _press(browser, "tags-delete-selected")
                _wait_testid(browser, "tags-delete-confirm")
                _press(browser, "tags-delete-confirm-submit")
                browser.wait_for("!document.querySelector('[data-testid=tags-delete-confirm]')", "explicit tag deletion")
                after = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/tags", owner.token))
                assert "calibration" not in {item["tag"] for item in after["items"]}
                assert "lighthouse" in {item["tag"] for item in after["items"]}
    finally:
        accounts.cleanup()
