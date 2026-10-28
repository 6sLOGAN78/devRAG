"""Saved One document choice covers disjoint pages beyond the scheduler batch boundary."""

import pytest
from pathlib import Path
from test.helpers.accounts import AccountRegistry
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.ingest import upload_text
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import api, ok
from test.testcases.test_spa_ingestion_browser import Scene, _press
from test.testcases.test_spa_browser import _set_viewport, _wait_testid

pytestmark = pytest.mark.e2e


def test_saved_one_document_choice_covers_all_selected_pdf_pages(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "one-doc")
            dataset = ok(create(ingress, owner))["id"]
            body = (repo_root / "test/fixtures/phase6/one-document-original.pdf").read_bytes()
            doc = upload_text(ingress, owner, dataset, body, "whole.pdf", mime="application/pdf")
            scene = Scene(ingress, owner, fake, dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                _wait_testid(browser, "chunk-method-option-one")
                _press(browser, "chunk-method-option-one")
                browser.wait_for("document.querySelector('[data-testid=\"chunk-method-option-one\"]').checked", "One document selected")
                assert browser.evaluate("document.querySelector('[data-testid=\"field-chunk-size\"]').disabled")
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.screenshot(str(output / "one-document-choice.png"))
                _press(browser, "chunk-method-submit")
                browser.wait_for("!document.querySelector('[data-testid=\"chunk-method-dialog\"]')", "saved method")
            changed = ok(
                api(
                    ingress,
                    "PATCH",
                    f"/api/v1/datasets/{dataset}/documents/{doc['id']}",
                    owner.token,
                    body={"parser_config": {"pages": [[2, 3], [13, 14]], "layout_recognize": False, "chunk_token_num": 1}},
                )
            )
            assert changed["parser_id"] == "one"
            fake.reset()
            scene.parse(doc["id"])
            rows = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token))
            assert rows["total"] == 1
            row = rows["items"][0]
            assert {b["page"] for b in row["positions"]} == {2, 3, 13, 14}
            text = row["text"]
            for n in [2, 3, 13, 14]:
                assert f"SOURCE PAGE {n:02d}" in text
            for n in [1, 4, 5, 6, 7, 8, 9, 10, 11, 12]:
                assert f"SOURCE PAGE {n:02d}" not in text
            assert "LIGHTHOUSE 52" in text and "ORCHARD 9100" in text
            detail = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}", owner.token))
            assert detail["pages_total"] == 14
            from test.helpers.uploads import sql

            assert sql("SELECT COUNT(*) FROM `task` WHERE `doc_id`=%s", (doc["id"],))[0][0] == 1
            listing = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents", owner.token))
            selected = next(d for d in listing["items"] if d["id"] == doc["id"])
            assert selected["pages_total"] == 4
            calls = [r for r in fake.requests if r.path == "/v1/embeddings"]
            assert len(calls) == 1 and calls[0].body["input"] == [text]
    finally:
        accounts.cleanup()


def test_one_document_keeps_both_structured_tables_and_owned_crop_ids(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "one-tables")
            dataset = ok(create(ingress, owner))["id"]
            doc = upload_text(ingress, owner, dataset, (repo_root / "test/fixtures/phase6/table-spanned-original.pdf").read_bytes(), "whole-table.pdf", mime="application/pdf")
            path = f"/api/v1/datasets/{dataset}/documents/{doc['id']}"
            ok(api(ingress, "PATCH", path, owner.token, body={"parser_id": "one", "parser_config": {"layout_recognize": True, "chunk_token_num": 1}}))
            Scene(ingress, owner, fake, dataset).parse(doc["id"])
            result = ok(api(ingress, "GET", path + "/chunks", owner.token))
            assert result["total"] == 1
            chunk = result["items"][0]
            assert {p["page"] for p in chunk["positions"]} == {1, 2}
            assert len(chunk["tables"]) == 2
            ids = [t["asset_id"] for t in chunk["tables"]]
            assert len(set(ids)) == 2
            for identifier in ids:
                response = api(ingress, "GET", "/api/v1/documents/images/" + identifier, owner.token)
                assert response.status_code == 200 and response.content.startswith(b"\x89PNG\r\n\x1a\n")
            from common.settings import load_settings
            from common.doc_store.doc_store_base import index_name
            from rag.utils.es_conn import get_doc_store
            from test.helpers.doc_store_contract import search

            stored = search(get_doc_store(load_settings()), index_name(owner.tenant_id), [dataset], condition={"doc_id": [doc["id"]]}, select=["image_ids_kwd"]).hits
            assert len(stored) == 1 and stored[0]["image_ids_kwd"] == ids
    finally:
        accounts.cleanup()
