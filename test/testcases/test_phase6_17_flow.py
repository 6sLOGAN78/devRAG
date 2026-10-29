"""Member saves Email and retrieves the original decoded envelope and chosen body."""

from pathlib import Path
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


def test_email_saved_choice_and_original_envelope_source(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "email")
            dataset = ok(create(ingress, owner))["id"]
            path = repo_root / "test/fixtures/phase6/email-original.eml"
            doc = upload_text(ingress, owner, dataset, path.read_bytes(), path.name, mime="message/rfc822")
            scene = Scene(ingress, owner, fake, dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                _wait_testid(browser, "chunk-method-option-email")
                _press(browser, "chunk-method-option-email")
                _wait_testid(browser, "email-settings-note")
                _press(browser, "chunk-method-submit")
                browser.wait_for("!document.querySelector('[data-testid=chunk-method-dialog]')", "Email choice saved")
                detail = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}", owner.token))
                assert detail["parser_id"] == "email"
                scene.parse(doc["id"])
                chunks = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token))
                assert chunks["total"] >= 1 and all("Subject: 灯塔 calibration facts" in row["text"] for row in chunks["items"])
                scene.files(browser)
                _press(browser, "dataset-test-retrieval")
                _wait_testid(browser, "field-retrieval-question")
                _type_into(browser, "field-retrieval-question", "Lighthouse height 52 metres calibration 73 units")
                range_value(browser, "field-retrieval-threshold", 0)
                range_value(browser, "field-retrieval-weight", 0)
                _press(browser, "retrieval-run")
                _wait_testid(browser, "hit-card")
                _press(browser, "hit-source")
                browser.wait_for('document.querySelector(\'[data-testid="source-passage"]\')?.textContent.includes("52 metres")', "decoded original body")
                content = browser.evaluate("document.querySelector('[data-testid=source-passage]').textContent")
                assert "73 units" in content and "alice@example.test" in content and "Subject: 灯塔 calibration facts" in content
                assert "Ignored attachment:" in content and "ATTACHMENT_TRAP9999" not in content and "ALTERNATIVE_TRAP" not in content
                assert not browser.evaluate("Boolean(document.querySelector('[data-testid=source-preview]'))")
                browser.wait_for('document.querySelector(\'[data-testid="source-drawer"]\').getAnimations({subtree:true}).every(a=>a.playState!=="running")', "source motion settled")
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.screenshot(str(output / "email-envelope-source.png"))
    finally:
        accounts.cleanup()
