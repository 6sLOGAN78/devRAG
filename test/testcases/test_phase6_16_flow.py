"""Saved Audio settings and separately bounded real local speech source journey."""

from pathlib import Path
import time
import json

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


def select_audio(browser):
    _press(browser, "document-more")
    _press(browser, "document-menu-chunking")
    _wait_testid(browser, "chunk-method-option-audio")
    _press(browser, "chunk-method-option-audio")
    _wait_testid(browser, "audio-settings-note")
    assert browser.evaluate("document.querySelector('[data-testid=field-chunk-size]').disabled")


def test_audio_choice_persists_without_automatically_transcribing(ingress, repo_root):
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "audio-config")
            dataset = ok(create(ingress, owner))["id"]
            path = repo_root / "test/fixtures/phase6/audio-original.wav"
            doc = upload_text(ingress, owner, dataset, path.read_bytes(), path.name, mime="audio/wav")
            scene = Scene(ingress, owner, fake, dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                select_audio(browser)
                _type_into(browser, "field-audio-language", "en")
                _press(browser, "chunk-method-submit")
                browser.wait_for("!document.querySelector('[data-testid=chunk-method-dialog]')", "Audio settings saved")
                detail = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}", owner.token))
                assert detail["parser_id"] == "audio" and detail["audio_language"] == "en" and detail["run"] == "0"
                scene.files(browser)
                _press(browser, "document-more")
                _press(browser, "document-menu-chunking")
                browser.wait_for("document.querySelector('[data-testid=field-audio-language]')?.value==='en'", "Saved Audio language reopened")
    finally:
        accounts.cleanup()


@pytest.mark.live_model
def test_exact_local_mp3_caption_timestamps_and_retrieved_audio_source(ingress, repo_root):
    from test.helpers.phase6_asr_budget import spend
    accounts = AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner = workspace(ingress, accounts, fake, "audio-source")
            spend("save-probe")
            ok(api(ingress, "PUT", "/api/v1/providers", owner.token, body={"tenant_id":owner.tenant_id,"provider":"deepdoc","instance_name":"default","models":[{"name":"faster-whisper-tiny","type":"asr"}]}))
            dataset = ok(create(ingress, owner))["id"]
            path = repo_root / "test/fixtures/phase6/audio-original.mp3"
            doc = upload_text(ingress, owner, dataset, path.read_bytes(), path.name, mime="audio/mpeg")
            scene = Scene(ingress, owner, fake, dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                select_audio(browser)
                browser.wait_for('Boolean(document.querySelector(\'[data-testid="field-asr-model"] option[value="faster-whisper-tiny@DeepDoc"]\'))', "configured speech model")
                choose(browser, "field-asr-model", "faster-whisper-tiny@DeepDoc")
                _type_into(browser, "field-audio-language", "en")
                _press(browser, "chunk-method-submit")
                browser.wait_for("!document.querySelector('[data-testid=chunk-method-dialog]')", "Audio model saved")
                spend("mp3-worker-browser")
                started = time.monotonic()
                scene.parse(doc["id"])
                elapsed = time.monotonic() - started
                chunks = ok(api(ingress, "GET", f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks", owner.token))
                text = " ".join(row["text"] for row in chunks["items"]).lower()
                assert all(row["audio"]["start"] < row["audio"]["end"] and row["positions"] == [] for row in chunks["items"])
                evidence=Path("ragflow-logs/phase6-16-mp3-result.json")
                evidence.write_text(json.dumps({"elapsed_seconds":elapsed,"chunks":chunks},indent=2)+"\n")
                scene.files(browser)
                _press(browser, "dataset-test-retrieval")
                _wait_testid(browser, "field-retrieval-question")
                _type_into(browser, "field-retrieval-question", "lighthouse calibration")
                range_value(browser, "field-retrieval-threshold", 0)
                range_value(browser, "field-retrieval-weight", 0)
                _press(browser, "retrieval-run")
                _wait_testid(browser, "hit-card")
                _press(browser, "hit-source")
                _wait_testid(browser, "source-audio")
                assert "seconds" in browser.evaluate("document.querySelector('[data-testid=source-audio]').textContent")
                assert not browser.evaluate("Boolean(document.querySelector('[data-testid=source-preview]'))")
                browser.wait_for('document.querySelector(\'[data-testid="source-drawer"]\').getAnimations({subtree:true}).every(a=>a.playState!=="running")', "source motion settled")
                output = Path("output/playwright/phase6-review")
                output.mkdir(parents=True, exist_ok=True)
                browser.screenshot(str(output / "audio-timestamp-source.png"))
                from test.helpers.phase6_asr_accuracy import assert_audio_facts
                assert_audio_facts(text)
    finally:
        accounts.cleanup()
