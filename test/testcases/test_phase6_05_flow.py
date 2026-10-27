"""Real extracted figures through upload, worker, owned download and Chrome source drawer."""

import hashlib
from pathlib import Path

import pytest

from test.helpers.accounts import AccountRegistry
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.ingest import chunk_texts, start_parse, upload_text, wait_run
from test.helpers.uploads import sql
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import api, join, ok
from test.testcases.test_spa_browser import _set_viewport, _type_into, _wait_testid
from test.testcases.test_spa_chat_browser import range_value
from test.testcases.test_spa_ingestion_browser import Scene, _press

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("suffix", ["docx", "pptx", "pdf"])
def test_extracted_figures_are_current_owned_pngs_and_survive_reparse(ingress, repo_root, suffix):
    registry = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, registry, fake, "figures")
            foreign = registry.register(prefix="foreign-figure")
            dataset = ok(create(ingress, owner))["id"]
            filename = "figures-mixed.pdf" if suffix == "pdf" else f"figures-duplicate.{suffix}"
            original = (repo_root / "test/fixtures/phase6" / filename).read_bytes()
            mime = {
                "pdf": "application/pdf",
                "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            }[suffix]
            doc = upload_text(ingress, owner, dataset, original, filename, mime=mime)
            doc_id = doc["id"]
            detail_path = f"/api/v1/datasets/{dataset}/documents/{doc_id}"
            scene = Scene(ingress, owner, fake, dataset)
            scene.parse(doc_id)
            detail = ok(api(ingress, "GET", detail_path, owner.token))
            assets = detail.get("assets", [])
            assert len(assets) == 1, "actual extracted bytes must reach owned document detail and deduplicate"
            asset = assets[0]
            assert set(asset) == {"id", "kind", "caption", "page", "width", "height"}
            assert asset["width"] == 1400 and asset["height"] == 400
            path = "/api/v1/documents/images/" + asset["id"]
            response = api(ingress, "GET", path, owner.token)
            assert response.status_code == 200 and response.content.startswith(b"\x89PNG\r\n\x1a\n")
            assert response.headers["content-type"].startswith("image/png")
            assert response.headers["cache-control"] == "private, no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            digest = sql("SELECT `sha256` FROM `document_asset` WHERE `id`=%s", (asset["id"],))[0][0]
            assert hashlib.sha256(response.content).hexdigest() == digest
            unauthorized = api(ingress, "GET", path, foreign.token)
            unknown = api(ingress, "GET", "/api/v1/documents/images/" + "0" * 32, foreign.token)
            assert unauthorized.status_code == unknown.status_code == 404 and unauthorized.json() == unknown.json()
            join(ingress, owner, foreign, role="admin")
            private = api(ingress, "GET", path, foreign.token)
            assert private.status_code == 404 and private.json() == unknown.json(), "membership/admin must not bypass a private source"
            ingress.cookies.clear()
            assert ingress.get(path).status_code == 401
            chunks = chunk_texts(api, ingress, owner.token, dataset, doc_id)
            text = "\n".join(c["text"] for c in chunks)
            assert ("MIXED NATIVE FACT 73" if suffix == "pdf" else "IMAGE ARCHIVE FACT: orchard harvest 9100 kilograms.") in text
            assert "content_base64" not in str(chunks) and digest not in str(chunks)
            if suffix == "docx":
                with ChromeSession() as browser:
                    _set_viewport(browser)
                    scene.files(browser)
                    _press(browser, "dataset-test-retrieval")
                    _wait_testid(browser, "field-retrieval-question")
                    _type_into(browser, "field-retrieval-question", "orchard harvest 9100 kilograms")
                    range_value(browser, "field-retrieval-threshold", 0)
                    range_value(browser, "field-retrieval-weight", 0)
                    _press(browser, "retrieval-run")
                    _wait_testid(browser, "hit-card")
                    _press(browser, "hit-source")
                    browser.wait_for(
                        "(() => { const i=document.querySelector('[data-testid=\"source-asset-image\"]'); return i?.complete && i.naturalWidth===1400; })()",
                        "authenticated extracted figure",
                        timeout=60,
                    )
                    assert browser.evaluate("document.querySelector('[data-testid=\"source-asset-image\"]').src.startsWith('blob:')")
                    assert browser.evaluate("document.querySelector('[data-testid=\"source-drawer\"] img[onerror]') === null")
                    out = Path("output/playwright/phase6-review")
                    out.mkdir(parents=True, exist_ok=True)
                    browser.screenshot(str(out / "owned-office-figure.png"))
            assert start_parse(ingress, owner, dataset, [doc_id], confirm=True).status_code == 200
            wait_run(ingress, owner, dataset, doc_id, "3", timeout=150)
            assert ok(api(ingress, "GET", detail_path, owner.token))["assets"][0]["id"] == asset["id"]
            assert len(sql("SELECT `id` FROM `document_asset` WHERE `doc_id`=%s", (doc_id,))) == 1
            if suffix == "pptx":
                deleted = api(ingress, "DELETE", "/api/v1/datasets", owner.token, body={"ids": [dataset]})
            else:
                deleted = api(ingress, "DELETE", f"/api/v1/datasets/{dataset}/documents", owner.token, body={"ids": [doc_id]})
            assert deleted.status_code == 200
            assert api(ingress, "GET", path, owner.token).status_code == 404
            assert sql("SELECT `id` FROM `document_asset` WHERE `doc_id`=%s", (doc_id,)) == []
    finally:
        registry.cleanup()
