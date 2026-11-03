"""RAPTOR browser journey: a summary must cite a real source passage."""
import pytest
from pathlib import Path

from test.helpers.accounts import AccountRegistry
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.ingest import upload_text
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import CHAT_ID, DEFAULTS, create, workspace
from test.testcases.test_provider_flow import api, ok
from test.testcases.test_spa_ingestion_browser import Scene, _press
from test.testcases.test_spa_browser import _type_into
from test.testcases.test_phase6_14_flow import range_value
from test.testcases.test_spa_browser import _set_viewport

pytestmark = pytest.mark.e2e


def test_raptor_job_emits_authorized_source_leaves(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "raptor")
            ok(api(ingress, "PATCH", DEFAULTS, owner.token, body={"chat": CHAT_ID}))
            dataset = ok(create(ingress, owner))["id"]
            ok(api(ingress, "PUT", f"/api/v1/datasets/{dataset}", owner.token,
                   body={"parser_config": {"chunk_token_num": 32, "delimiter": "\n", "overlapped_percent": 0}}))
            doc = upload_text(ingress, owner, dataset, (repo_root / "test/fixtures/phase6/raptor-original.txt").read_bytes(), "raptor.txt")
            scene = Scene(ingress, owner, fake, dataset)
            scene.parse(doc["id"])
            assert scene.chunk_total(doc["id"]) == 6
            fake.chat_responses[:] = [f"Pair {i}: two inspections agree on lighthouse height 52 metres and calibration offset 73 units." for i in range(3)] + ["All six inspections agree on a 52 metre lighthouse and a 73 unit calibration offset."]
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "dataset-jobs-open")
                _press(browser, "dataset-raptor-start")
                def started():
                    rows = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/jobs", owner.token))["items"]
                    return next((row for row in rows if row["type"] == "raptor"), None)
                job = wait_until(started, timeout=30)
                def finished():
                    row = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/jobs/{job['id']}", owner.token))
                    return row if row["run"] in {"3", "4"} else None
                assert wait_until(finished, timeout=90)["run"] == "3"
                browser.wait_for("document.querySelector('[data-testid=dataset-job-progress]')?.textContent.includes('Done · 1 of 1 summary generations complete')", "completed RAPTOR job visible")
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.evaluate("document.querySelector('[data-testid=dataset-job-row]').scrollIntoView({block:'center'})")
                browser.screenshot(str(output / "raptor-job.png"))
                scene.files(browser)
                _press(browser, "dataset-test-retrieval")
                browser.wait_for("!!document.querySelector('[data-testid=field-retrieval-question]')", "retrieval controls")
                _type_into(browser, "field-retrieval-question", "What is the lighthouse height and calibration offset?")
                range_value(browser, "field-retrieval-threshold", 0)
                range_value(browser, "field-retrieval-weight", 0)
                _press(browser, "retrieval-run")
                browser.wait_for("[...document.querySelectorAll('[data-testid=hit-card]')].some(card => card.textContent.includes('All six inspections'))", "top RAPTOR summary hit")
                browser.evaluate("[...document.querySelectorAll('[data-testid=hit-card]')].find(card => card.textContent.includes('All six inspections')).querySelector('[data-testid=hit-source]').click()")
                browser.wait_for("!!document.querySelector('[data-testid=source-leaves]')?.querySelector('button')", "original source list")
                browser.evaluate("document.querySelector('[data-testid=source-leaves] button').click()")
                browser.wait_for("!!document.querySelector('[data-testid=source-back-summary]') && document.querySelector('[data-testid=source-passage]')?.textContent.includes('lighthouse')", "authorized original leaf passage")
                original = browser.evaluate("document.querySelector('[data-testid=source-passage]').textContent")
                assert "All six inspections" not in original and "52" in original
                browser.wait_for("document.querySelector('[data-testid=source-drawer]').getAnimations({subtree:true}).every(animation => animation.playState !== 'running')", "source drawer motion settled")
                browser.screenshot(str(output / "raptor-original-citation.png"))
            assert ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}", owner.token))["parser_config"]["raptor"] is True
            result = ok(api(ingress, "POST", "/api/v1/datasets/search", owner.token,
                            body={"dataset_ids": [dataset], "question": "What is the lighthouse height?", "similarity_threshold": 0}))
            summaries = [row for row in result["chunks"] if row.get("summary_level")]
            assert {row["summary_level"] for row in summaries} == {1, 2}
            assert all(row.get("source_leaves") for row in summaries)
            assert any(doc["id"] in {leaf["doc_id"] for leaf in row["source_leaves"]} for row in summaries)
    finally:
        accounts.cleanup()
