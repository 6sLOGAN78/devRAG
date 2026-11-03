"""A member downloads an owned RAPTOR artifact and deletes only its derived index."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from test.helpers.accounts import AccountRegistry
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.ingest import upload_text
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import CHAT_ID, DEFAULTS, create, workspace
from test.testcases.test_provider_flow import api, ok
from test.testcases.test_spa_browser import _set_viewport
from test.testcases.test_spa_ingestion_browser import Scene, _press, _press_expr

pytestmark = pytest.mark.e2e


def test_download_history_and_derived_only_delete_through_browser(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "artifact")
            ok(api(ingress, "PATCH", DEFAULTS, owner.token, body={"chat": CHAT_ID}))
            dataset = ok(create(ingress, owner))["id"]
            ok(api(ingress, "PUT", f"/api/v1/datasets/{dataset}", owner.token,
                   body={"parser_config": {"chunk_token_num": 32, "delimiter": "\n", "overlapped_percent": 0}}))
            source = (repo_root / "test/fixtures/phase6/raptor-original.txt").read_bytes()
            doc = upload_text(ingress, owner, dataset, source, "artifact-original.txt")
            scene = Scene(ingress, owner, fake, dataset)
            scene.parse(doc["id"])
            original = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token,
                              params={"size": "100"}))
            original_ids = {row["id"] for row in original["items"]}
            assert len(original_ids) == 6
            fake.chat_responses[:] = [f"Pair {i}: lighthouse height 52 metres and calibration offset 73 units." for i in range(3)] + [
                "All six original inspections agree: lighthouse height 52 metres, offset 73 units."]
            with ChromeSession() as browser, tempfile.TemporaryDirectory(prefix="devrag-artifact-") as download_dir:
                _set_viewport(browser)
                browser.allow_downloads(download_dir)
                scene.files(browser)
                _press(browser, "dataset-jobs-open")
                _press(browser, "dataset-raptor-start")

                def finished():
                    rows = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/jobs", owner.token))["items"]
                    return next((row for row in rows if row["type"] == "raptor" and row["run"] == "3" and row.get("artifact_filename")), None)

                job = wait_until(finished, timeout=90)
                filename = job["artifact_filename"]
                browser.wait_for("!!document.querySelector('[data-testid=dataset-job-artifact]')", "generated artifact download")
                _press(browser, "dataset-job-artifact")
                downloaded = Path(download_dir) / filename
                wait_until(lambda: downloaded if downloaded.exists() else None, timeout=20)
                payload = json.loads(downloaded.read_bytes())
                assert payload["generation"] == job["id"] and len(payload["summaries"]) == 4
                assert "52" in payload["summaries"][-1]["text"] and "73" in payload["summaries"][-1]["text"]
                assert set(payload["summaries"][-1]["source_leaf_ids"]) == original_ids
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.screenshot(str(output / "artifact-download.png"))

                _press(browser, "dataset-raptor-delete")
                browser.wait_for("!!document.querySelector('[role=alertdialog]')", "derived deletion confirmation")
                assert "original" in str(browser.evaluate("document.querySelector('[role=alertdialog]').textContent")).lower()
                _press_expr(browser, "[...document.querySelectorAll('[role=alertdialog] button')].at(-1)", "confirm RAPTOR deletion")
                browser.wait_for("!!document.querySelector('[data-testid=dataset-raptor-deleted]')", "derived deletion result")
                assert "4" in str(browser.evaluate("document.querySelector('[data-testid=dataset-raptor-deleted]').textContent"))
                history_api = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/artifacts/alteration", owner.token))
                assert history_api["total"] == 1 and history_api["items"][0]["deleted_count"] == 4
                _press(browser, "dataset-alteration-open")
                browser.wait_for("!!document.querySelector('[data-testid=dataset-alteration-history]')", "alteration history drawer")
                try:
                    browser.wait_for("!!document.querySelector('[data-testid=dataset-alteration-row]')", "alteration history")
                except TimeoutError:
                    raise AssertionError(str(browser.evaluate("document.querySelector('[data-testid=dataset-alteration-history]')?.textContent"))) from None
                assert "4" in str(browser.evaluate("document.querySelector('[data-testid=dataset-alteration-row]').textContent"))
                browser.screenshot(str(output / "artifact-deleted-history.png"))

            after = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token,
                           params={"size": "100"}))
            assert {row["id"] for row in after["items"]} == original_ids
            assert ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}", owner.token))["id"] == doc["id"]
            assert api(ingress, "GET", f"/api/v1/documents/artifact/{filename}", owner.token).status_code == 404
            history = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/artifacts/alteration", owner.token))
            assert history["total"] == 1 and history["items"][0]["deleted_count"] == 4
    finally:
        accounts.cleanup()
