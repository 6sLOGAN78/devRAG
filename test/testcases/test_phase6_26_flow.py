"""Optional PDF choices appear only for configured services in the real browser."""

import json

import pytest

from test.helpers.accounts import AccountRegistry
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.ingest import chunk_texts, start_parse, upload_text, wait_run
from test.helpers.planted import planted_pdf
from test.helpers.uploads import sql
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import api, ok
from test.testcases.test_spa_browser import _set_viewport
from test.testcases.test_spa_ingestion_browser import Scene, _press

pytestmark = pytest.mark.e2e


def test_pdf_parser_choices_match_operator_configuration_without_exposing_addresses(ingress):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "backend-choice")
            dataset = ok(create(ingress, owner))["id"]
            doc = upload_text(ingress, owner, dataset, planted_pdf(), "backend-source.pdf", mime="application/pdf")
            names = ok(api(ingress, "GET", "/api/v1/parser-backends", owner.token))["available"]
            assert "deepdoc" in names
            assert all(name in {"deepdoc", "docling", "mineru"} for name in names)
            scene = Scene(ingress, owner, fake, dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                browser.wait_for("!!document.querySelector('[data-testid=field-layout]')", "PDF parser settings")
                browser.wait_for("!!document.querySelector('[data-testid=field-chunk-size]')", "chunking form")
                options = browser.evaluate("[...document.querySelectorAll('[data-testid=field-pdf-backend] option')].map(option=>option.value)")
                if any(name in names for name in ("docling", "mineru")):
                    browser.wait_for("!!document.querySelector('[data-testid=field-pdf-backend]')", "configured backend selection")
                    options = browser.evaluate("[...document.querySelectorAll('[data-testid=field-pdf-backend] option')].map(option=>option.value)")
                    assert set(options) == set(names)
                else:
                    assert options == []
            assert ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}", owner.token))["id"] == doc["id"]
    finally:
        accounts.cleanup()


@pytest.mark.live_model
@pytest.mark.parametrize(("backend", "fixture", "width", "height", "facts"), [
    ("docling", "docling-real-original.pdf", 600, 400, ("Lighthouse 52", "Owner", "73", "Status", "Ready")),
    ("mineru", "mineru416-real-original.pdf", 400, 200, ("Lighthouse 52", "Owner 73")),
])
def test_real_pdf_choice_saves_and_worker_indexes_source_backed_chunks(ingress, repo_root, backend, fixture, width, height, facts):
    """Run each case only with its pinned local parser service configured."""
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, f"{backend}-real")
            dataset = ok(create(ingress, owner))["id"]
            source = (repo_root / "test/fixtures/phase6" / fixture).read_bytes()
            doc = upload_text(ingress, owner, dataset, source, f"{backend}-source.pdf", mime="application/pdf")
            route = f"/api/v1/datasets/{dataset}/documents/{doc['id']}"
            scene = Scene(ingress, owner, fake, dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                browser.wait_for(f"!!document.querySelector('[data-testid=field-pdf-backend] option[value={backend}]')", f"{backend} available")
                browser.evaluate("(() => { const select = document.querySelector('[data-testid=field-pdf-backend]');"
                                 f"select.value = '{backend}'; select.dispatchEvent(new Event('change', {{bubbles:true}})); }})()")
                browser.wait_for(f"document.querySelector('[data-testid=field-pdf-backend]').value === '{backend}'", f"{backend} selected")
                _press(browser, "chunk-method-submit")
                browser.wait_for("!document.querySelector('[data-testid=chunk-method-dialog]')", f"{backend} choice saved")
                assert ok(api(ingress, "GET", route, owner.token))["layout_recognize"] == backend

                started = start_parse(ingress, owner, dataset, [doc["id"]])
                assert started.status_code == 200, started.text
                row = wait_run(ingress, owner, dataset, doc["id"], "3", timeout=150)
                chunks = chunk_texts(api, ingress, owner.token, dataset, doc["id"])
                assert row["chunk_count"] == len(chunks) and chunks
                text = "\n".join(chunk["text"] for chunk in chunks)
                assert all(fact in text for fact in facts), text
                boxes = [box for chunk in chunks for box in chunk["positions"]]
                assert boxes and all(box["page"] == 1 for box in boxes)
                assert all(0 <= box["x0"] < box["x1"] <= width and 0 <= box["top"] < box["bottom"] <= height for box in boxes)
                records = sql("SELECT `dsl` FROM `pipeline_operation_log` WHERE `document_id`=%s", (doc["id"],))
                ledgers = [json.loads(raw) if isinstance(raw, str) else raw for (raw,) in records]
                assert any(entry.get("layout_backend") == backend and entry.get("layout_regions", 0) >= len(facts) // 2
                           for entry in ledgers), ledgers
    finally:
        accounts.cleanup()
