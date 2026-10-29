"""Member configures vision, saves Picture and retrieves a caption with its actual image."""

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
from test.testcases.test_spa_chat_browser import choose, range_value

pytestmark = pytest.mark.e2e


def test_picture_choice_vision_model_caption_and_owned_source_image(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "picture")
            ok(api(ingress, "POST", "/api/v1/providers/openai-compatible/instances", owner.token, body={"tenant_id": owner.tenant_id, "instance_name":"default", "models": [{"name": "fake-vision", "type": "vision"}]}))
            dataset = ok(create(ingress, owner))["id"]
            p = repo_root / "test/fixtures/phase6/picture-original.png"
            doc = upload_text(ingress, owner, dataset, p.read_bytes(), p.name, mime="image/png")
            scene = Scene(ingress, owner, fake, dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                _wait_testid(browser, "chunk-method-option-picture")
                _press(browser, "chunk-method-option-picture")
                browser.wait_for('Boolean(document.querySelector(\'[data-testid="field-image-model"] option[value="fake-vision@OpenAI-API-Compatible"]\'))', "configured vision option")
                choose(browser, "field-image-model", "fake-vision@OpenAI-API-Compatible")
                _press(browser, "chunk-method-submit")
                browser.wait_for("!document.querySelector('[data-testid=\"chunk-method-dialog\"]')", "Picture choice saved")
                detail = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}", owner.token))
                assert detail["parser_id"] == "picture" and detail["image_model"] == "fake-vision@OpenAI-API-Compatible"
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                _wait_testid(browser, "field-image-model")
                browser.wait_for('document.querySelector(\'[data-testid="field-image-model"]\')?.value==="fake-vision@OpenAI-API-Compatible"', "persisted vision selection")
                assert browser.evaluate("document.querySelector('[data-testid=\"field-image-model\"]').value") == "fake-vision@OpenAI-API-Compatible"
                browser.evaluate('document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}))')
                scene.parse(doc["id"])
                chunks = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token))
                assert chunks["total"] == 1 and "52 metres" in chunks["items"][0]["text"]
                scene.files(browser)
                _press(browser, "dataset-test-retrieval")
                _wait_testid(browser, "field-retrieval-question")
                _type_into(browser, "field-retrieval-question", "lighthouse red roof 52 metres")
                range_value(browser, "field-retrieval-threshold", 0)
                range_value(browser, "field-retrieval-weight", 0)
                _press(browser, "retrieval-run")
                _wait_testid(browser, "hit-card")
                _press(browser, "hit-source")
                browser.wait_for('document.querySelector(\'[data-testid="source-passage"]\')?.textContent.includes("52 metres")', "real caption")
                browser.wait_for(
                    "Array.from(document.querySelectorAll('[data-testid=\"source-asset-image\"]')).some(i=>i.complete && i.naturalWidth===640 && i.naturalHeight===480)", "owned original image loaded"
                )
                assert browser.evaluate("document.querySelector('[data-testid=\"source-passage\"]').textContent").find("73 units") >= 0
                assert not browser.evaluate("Boolean(document.querySelector('[data-testid=\"source-preview\"]'))")
                browser.wait_for('document.querySelector(\'[data-testid="source-drawer"]\').getAnimations({subtree:true}).every(a=>a.playState!=="running")', "source motion settled")
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.screenshot(str(output / "picture-caption-source.png"))
    finally:
        accounts.cleanup()
