"""A real worker refreshes existing chunks and Chrome displays the owned job."""
import json
from pathlib import Path

import pytest

from common.settings import get_settings
from rag.queue.factory import get_queue
from test.helpers.accounts import AccountRegistry
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.ingest import upload_text
from test.helpers.uploads import sql
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import CHAT_ID, create, workspace
from test.testcases.test_provider_flow import api, ok
from test.testcases.test_spa_browser import _set_viewport
from test.testcases.test_spa_ingestion_browser import Scene, _press

pytestmark = pytest.mark.e2e


def test_browser_shows_completed_dataset_refresh_without_reparsing(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "dataset-job")
            dataset = ok(create(ingress, owner))["id"]
            scene = Scene(ingress, owner, fake, dataset)
            source = (repo_root / "test/fixtures/phase6/controlled-enrichment-original.txt").read_bytes()
            doc = upload_text(ingress, owner, dataset, source, "job-original.txt")
            scene.parse(doc["id"])
            before_chunk = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token))["items"][0]
            before_parse_task = sql("SELECT `id` FROM `task` WHERE `doc_id`=%s AND `task_type`='parse'", (doc["id"],))[0][0]
            ok(api(ingress, "PUT", f"/api/v1/datasets/{dataset}", owner.token,
                   body={"parser_config": {"auto_tags": True, "allowed_tags": ["lighthouse", "calibration"], "tag_model_id": CHAT_ID}}))
            fake.chat_response = json.dumps({"items": [{"index": 0, "tags": ["lighthouse"]}]})
            before_calls = len(fake.chat_requests())
            job = ok(api(ingress, "POST", f"/api/v1/datasets/{dataset}/jobs", owner.token, body={"type": "enrich"}))
            assert job["total"] == 1 and job["type"] == "enrich"
            duplicate = sql("SELECT `id`, `digest` FROM `task` WHERE `doc_id`=%s AND `task_type`='dataset_enrich'", (job["id"],))[0]
            get_queue(get_settings()).enqueue(duplicate[0], duplicate[1], 0)
            detail = wait_until(lambda: _finished(ingress, owner.token, dataset, job["id"]), timeout=90)
            assert detail["run"] == "3" and detail["completed"] == 1 and detail["failed"] == 0
            assert len(fake.chat_requests()) == before_calls + 1
            after_chunk = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token))["items"][0]
            assert after_chunk["text"] == before_chunk["text"] == source.decode().strip()
            assert after_chunk["id"] == before_chunk["id"]
            tags = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/tags", owner.token))
            assert ("lighthouse", "generated") in {(row["tag"], row.get("origin")) for row in tags["items"]}
            assert sql("SELECT `id` FROM `task` WHERE `doc_id`=%s AND `task_type`='parse'", (doc["id"],))[0][0] == before_parse_task
            child_id = sql("SELECT `id` FROM `task` WHERE `doc_id`=%s AND `task_type`='dataset_enrich'", (job["id"],))[0][0]
            task = ok(api(ingress, "GET", f"/v1/task/status/{child_id}", owner.token))
            assert task["job_id"] == job["id"] and task["doc_id"] == "" and task["finished"] is True
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser, "dataset-jobs-open")
                browser.wait_for("document.querySelector('[data-testid=dataset-job-progress]')?.textContent.includes('1 of 1 documents complete')", "completed job visible")
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.evaluate("document.querySelector('[data-testid=dataset-job-row]').scrollIntoView({block:'center'})")
                browser.screenshot(str(output / "dataset-enrichment-job.png"))
    finally:
        accounts.cleanup()


def _finished(ingress, token, dataset, job_id):
    result = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/jobs/{job_id}", token))
    return result if result["run"] in {"2", "3", "4"} else None


def test_cancellation_during_model_call_does_not_publish_incomplete_labels(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "dataset-cancel")
            dataset = ok(create(ingress, owner))["id"]
            source = (repo_root / "test/fixtures/phase6/controlled-enrichment-original.txt").read_bytes()
            doc = upload_text(ingress, owner, dataset, source, "cancel-original.txt")
            Scene(ingress, owner, fake, dataset).parse(doc["id"])
            ok(api(ingress, "PUT", f"/api/v1/datasets/{dataset}", owner.token,
                   body={"parser_config": {"auto_tags": True, "allowed_tags": ["lighthouse"], "tag_model_id": CHAT_ID}}))
            fake.chat_mode = "gated_nonstream"
            fake.chat_response = json.dumps({"items": [{"index": 0, "tags": ["lighthouse"]}]})
            before = len(fake.chat_requests())
            job = ok(api(ingress, "POST", f"/api/v1/datasets/{dataset}/jobs", owner.token, body={"type": "enrich"}))
            wait_until(lambda: len(fake.chat_requests()) == before + 1, timeout=30)
            cancelled = ok(api(ingress, "POST", f"/api/v1/datasets/{dataset}/jobs/{job['id']}/cancel", owner.token))
            assert cancelled["run"] == "2"
            child_id = sql("SELECT `id` FROM `task` WHERE `doc_id`=%s AND `task_type`='dataset_enrich'", (job["id"],))[0][0]
            fake.release_chat()
            queue = get_queue(get_settings())
            wait_until(lambda: not any(fields.get("task_id") == child_id for _, fields in queue._client.xrange(queue._normal)), timeout=30)
            tags = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/tags", owner.token))
            assert all(row["tag"] != "lighthouse" for row in tags["items"])
            assert ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/jobs/{job['id']}", owner.token))["run"] == "2"
    finally:
        accounts.cleanup()
