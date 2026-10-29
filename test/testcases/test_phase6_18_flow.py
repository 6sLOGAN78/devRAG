"""Saved Resume controls and source-backed structured résumé retrieval in actual Chrome."""
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


def test_resume_choice_reopens_and_retrieves_original_work_section(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "resume")
            dataset = ok(create(ingress, owner))["id"]
            path = repo_root / "test/fixtures/phase6/resume-original.txt"
            doc = upload_text(ingress,owner,dataset,path.read_bytes(),path.name)
            scene = Scene(ingress,owner,fake,dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser,"document-more")
                _press(browser,"document-menu-chunking")
                _wait_testid(browser,"chunk-method-option-resume")
                _press(browser,"chunk-method-option-resume")
                _wait_testid(browser,"resume-settings-note")
                assert browser.evaluate("document.querySelector('[data-testid=field-resume-model]').disabled")
                _press(browser,"field-resume-use-model")
                assert not browser.evaluate("document.querySelector('[data-testid=field-resume-model]').disabled")
                _press(browser,"chunk-method-submit")
                browser.wait_for("!document.querySelector('[data-testid=chunk-method-dialog]')","Resume choice saved")
                detail=ok(api(ingress,"GET",f"/api/v1/datasets/{dataset}/documents/{doc['id']}",owner.token))
                assert detail["parser_id"]=="resume" and detail["resume_use_model"] is True
                scene.files(browser)
                _press(browser,"document-more")
                _press(browser,"document-menu-chunking")
                browser.wait_for("document.querySelector('[data-testid=field-resume-use-model]')?.checked","inference opt-in persisted")
                browser.evaluate("[...document.querySelectorAll('[data-testid=chunk-method-dialog] button')].find(b=>b.textContent.trim()==='Close').click()")
                browser.wait_for("!document.querySelector('[data-testid=chunk-method-dialog]')","settings closed")
                before=len(fake.chat_requests())
                scene.parse(doc["id"])
                assert len(fake.chat_requests())==before  # Clear headings require no inference.
                chunks=ok(api(ingress,"GET",f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks",owner.token))
                assert chunks["total"]>=5
                all_text="\n".join(c["text"] for c in chunks["items"])
                assert "Mira Sen" in all_text and "mira.sen@example.test" in all_text and "Phone" not in all_text
                scene.files(browser)
                _press(browser,"dataset-test-retrieval")
                _wait_testid(browser,"field-retrieval-question")
                _type_into(browser,"field-retrieval-question","lighthouse height 52 metres calibration offset 73 units")
                range_value(browser,"field-retrieval-threshold",0)
                range_value(browser,"field-retrieval-weight",0)
                _press(browser,"retrieval-run")
                _wait_testid(browser,"hit-card")
                _press(browser,"hit-source")
                browser.wait_for('document.querySelector(\'[data-testid="source-passage"]\')?.textContent.includes("52 metres")',"original résumé measurement evidence")
                content=browser.evaluate("document.querySelector('[data-testid=source-passage]').textContent")
                assert "73 units" in content and "Resume / Work History" in content
                assert not browser.evaluate("Boolean(document.querySelector('[data-testid=source-preview]'))")
                browser.wait_for('document.querySelector(\'[data-testid="source-drawer"]\').getAnimations({subtree:true}).every(a=>a.playState!=="running")',"source motion settled")
                output=Path("output/playwright/phase6-review")
                output.mkdir(parents=True,exist_ok=True)
                browser.screenshot(str(output/"resume-work-source.png"))
    finally:
        accounts.cleanup()
