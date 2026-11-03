"""Optional PDF choices appear only for configured services in the real browser."""

import pytest

from test.helpers.accounts import AccountRegistry
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.ingest import upload_text
from test.helpers.planted import planted_pdf
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
