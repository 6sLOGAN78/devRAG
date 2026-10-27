"""Real Chrome chat journeys. The criterion-5 case uses real providers; supporting scenes use the local provider."""
# ruff: noqa: F811
from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry, unique_email, unique_name
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import FakeProvider, fake_provider_stack  # noqa: F401
from test.helpers.planted import FACTS, PDF_FACTS, off_topic_question, planted_pdf, planted_txt
from test.testcases.conftest import BASE_URL
from test.testcases.test_chat_flow import assistant
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_live_models import LiveEnv, live_env  # noqa: F401
from test.testcases.test_provider_flow import api, ok, registry  # noqa: F401
from test.testcases.test_retrieval_flow import RERANK_ID, save_rerank_model
from test.testcases.test_spa_browser import _by_id, _close_upload_dialog, _type_into, _upload_through_dialog, _wait_testid
from test.testcases.test_spa_ingestion_browser import (
    ORIGIN,  # noqa: F401
    SCREENSHOT_DIR,
    Scene,
    _assert_box_inside_image,
    _press,
    _press_expr,
    browser,  # noqa: F401 (fixture)
)

pytestmark = pytest.mark.e2e
HOSTILE = '<script>window.__x=1</script> <img src=x onerror="window.__x=1"> ##9$$'


def choose(browser: ChromeSession, test_id: str, value: str) -> None:
    browser.evaluate(f"(() => {{ const e = {_by_id(test_id)}; e.value = {json.dumps(value)}; e.dispatchEvent(new Event('change', {{bubbles:true}})); }})()")
    browser.wait_for(f"{_by_id(test_id)}.value === {json.dumps(value)}", "the selected option")


def range_value(browser: ChromeSession, test_id: str, value: float) -> None:
    # The native setter avoids React's value tracker, then fires the same bubbling input event as a slider.
    browser.evaluate(
        f"(() => {{ const e = {_by_id(test_id)};"
        f" Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(e, {json.dumps(str(value))});"
        " e.dispatchEvent(new Event('input', {bubbles:true})); })()"
    )


def question(browser: ChromeSession, text: str) -> None:
    _wait_testid(browser, "chat-input")
    _type_into(browser, "chat-input", text)
    browser.wait_for(f"{_by_id('chat-send')}?.getAttribute('aria-disabled') !== 'true'", "Send enabled")
    _press(browser, "chat-send")


def completed(browser: ChromeSession) -> None:
    browser.wait_for("document.querySelector('[data-testid=\"message-assistant\"][data-finish=\"complete\"]') !== null", "the completed answer", timeout=120)
    _wait_testid(browser, "chat-send")


def answer_text(browser: ChromeSession) -> str:
    return str(browser.evaluate("document.querySelector('[data-testid=\"message-assistant\"] > div:last-child > div')?.textContent ?? ''"))


def open_first_citation(browser: ChromeSession) -> None:
    _wait_testid(browser, "cite-pill")
    _press(browser, "cite-pill")
    _wait_testid(browser, "source-passage")


@pytest.fixture
def chat_scene(stack_ready: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider):
    owner = workspace(stack_ready, registry, fake_provider_stack, "webchat")
    dataset = ok(create(stack_ready, owner, unique_name("Chat scene")))
    scene = Scene(stack_ready, owner, fake_provider_stack, dataset["id"])
    doc_id = scene.add(planted_txt(), "facts.txt")
    scene.parse(doc_id)
    chat = assistant(stack_ready, owner, dataset_ids=[dataset["id"]], vector_similarity_weight=0, similarity_threshold=0.2)
    try:
        yield SimpleNamespace(scene=scene, owner=owner, chat=chat, fake=fake_provider_stack)
    finally:
        fake_provider_stack.release_chat()
        fake_provider_stack.chat_pieces = None
        fake_provider_stack.chat_mode = "plain"


def open_chat(world, browser):
    world.scene.open(browser, f"/chats?chat={world.chat['id']}", "chat-input")


def test_stop_keeps_the_partial_answer_and_survives_a_reload(chat_scene, browser):
    world = chat_scene
    world.fake.hold_chat()
    world.fake.chat_mode = "gated"
    open_chat(world, browser)
    question(browser, FACTS[0].question)
    browser.wait_for("document.querySelector('[data-testid=\"message-assistant\"]')?.textContent.includes('Start')", "first delta")
    _press(browser, "chat-stop")
    _wait_testid(browser, "message-stopped")
    before = answer_text(browser)
    assert before
    browser.navigate(browser.evaluate("location.href"))
    _wait_testid(browser, "message-stopped")
    assert answer_text(browser) == before
    assert browser.evaluate(f"{_by_id('chat-input')}.readOnly") is False


def test_off_topic_question_shows_the_configured_empty_response(chat_scene, browser):
    world = chat_scene
    open_chat(world, browser)
    before = len(world.fake.chat_requests())
    question(browser, off_topic_question())
    _wait_testid(browser, "message-empty-badge")
    assert world.chat["prompt_config"]["empty_response"] in browser.evaluate(f"{_by_id('message-assistant')}.textContent")
    assert browser.evaluate("document.querySelectorAll('[data-testid=\"cite-pill\"]').length") == 0
    assert len(world.fake.chat_requests()) == before


def test_markup_and_missing_marker_render_as_text(chat_scene, browser):
    world = chat_scene
    doc = world.scene.add(("Amber reactor safety note: " + HOSTILE).encode(), "hostile.txt")
    world.scene.parse(doc)
    world.fake.chat_pieces = ("Amber reactor safety note ", HOSTILE, " ##0$$")
    world.fake.chat_mode = "marker"
    open_chat(world, browser)
    question(browser, "Amber reactor safety note")
    completed(browser)
    assert browser.evaluate("window.__x === undefined") is True
    assert browser.evaluate("document.querySelector('[data-testid=\"message-assistant\"] script, [data-testid=\"message-assistant\"] img') === null") is True
    assert "<script>" in browser.evaluate(f"{_by_id('message-assistant')}.textContent")
    assert browser.evaluate("document.querySelector('[data-testid=\"cite-pill\"][data-cite-index=\"9\"]') === null") is True
    open_first_citation(browser)
    assert HOSTILE in browser.evaluate(f"{_by_id('source-passage')}.textContent")
    assert browser.evaluate("window.__x === undefined") is True


def test_retrieval_testing_page_threshold_weight_and_rerank(chat_scene, browser):
    world = chat_scene
    save_rerank_model(world.scene.ingress, world.owner, world.fake)
    world.scene.files(browser)
    _press(browser, "dataset-test-retrieval")
    _wait_testid(browser, "field-retrieval-question")
    _type_into(browser, "field-retrieval-question", FACTS[0].question)
    range_value(browser, "field-retrieval-threshold", 0)
    range_value(browser, "field-retrieval-weight", 0)
    def run():
        _press(browser, "retrieval-run")
        browser.wait_for(f"{_by_id('retrieval-results')} !== null && {_by_id('retrieval-run')}.getAttribute('aria-busy') !== 'true'", "retrieval finished")
        browser.wait_for(f"{_by_id('retrieval-stale')} === null", "current retrieval result")
    def scores(key):
        return browser.evaluate(
            "[...document.querySelectorAll('[data-testid=\"hit-card\"]')].map(e => ["
            "Number(e.querySelector('[data-testid=\"hit-score-overall\"]').textContent),"
            "Number(e.querySelector('[data-testid=\"hit-score-" + key + "\"]').textContent)])"
        )
    run()
    keyword = scores("term")
    assert keyword and all(abs(a-b) <= 0.001 for a, b in keyword)
    assert [a for a, _ in keyword] == sorted([a for a, _ in keyword], reverse=True)
    count = len(keyword)
    range_value(browser, "field-retrieval-threshold", 0.99)
    _wait_testid(browser, "retrieval-stale")
    run()
    assert browser.evaluate("document.querySelectorAll('[data-testid=\"hit-card\"]').length") < count
    range_value(browser, "field-retrieval-threshold", 0)
    range_value(browser, "field-retrieval-weight", 1)
    run()
    vectors = scores("vector")
    assert vectors and all(abs(a-b) <= 0.001 for a, b in vectors)
    assert [a for a, _ in vectors] == sorted([a for a, _ in vectors], reverse=True)
    choose(browser, "field-retrieval-rerank", RERANK_ID)
    run()
    _wait_testid(browser, "retrieval-reranked")
    _wait_testid(browser, "hit-score-rerank")
    assert FACTS[0].question not in browser.evaluate("location.href")


@pytest.mark.live_model
def test_criterion_5_register_to_cited_streamed_answer(stack_ready, registry, browser, live_env: LiveEnv):
    from test.testcases.test_live_chat import CHAT_TURN_CAP, QUERY_EMBED_CAP, STATE, TEI_MODEL, usage_count

    # When run with the API live module, reserve the browser turn and fallback before spending.
    assert STATE.get("query_embeddings", 0) + 2 <= QUERY_EMBED_CAP
    assert STATE["turns"] + 3 <= CHAT_TURN_CAP  # Two provider-save tests and this browser turn.
    # Only provider setup uses the API. The credential never enters the browser.
    email, nickname, password = unique_email("coregate"), unique_name("Core gate"), "test-only-pass-0001"
    browser.navigate(f"{ORIGIN}/login?mode=register")
    _wait_testid(browser, "register-form")
    for field, value in (("field-nickname", nickname), ("field-email", email), ("field-password", password)):
        _type_into(browser, field, value)
    _press(browser, "register-submit")
    browser.wait_for("location.pathname === '/home'", "registered home", timeout=60)
    token = browser.evaluate("localStorage.getItem('Authorization')")
    assert token
    info = httpx.get(f"{BASE_URL}/v1/user/info", headers={"Authorization": f"Bearer {token}"}, timeout=10).json()["data"]
    owner = Account(email=email, password=password, nickname=nickname, user_id=info["id"], tenant_id=info["tenant_id"], token=token)
    registry.created.append(owner)
    def seed(method, path, body):
        response = api(stack_ready, method, path, token, body=body)
        assert response.status_code == 200 and response.json()["code"] == 0
    seed("PUT", "/api/v1/providers", {"provider": "OpenRouter", "api_key": live_env.key,
        "models": [{"name": live_env.chat_model, "type": "chat"}, {"name": live_env.embed_model, "type": "embedding"}]})
    seed("PUT", "/api/v1/providers", {"provider": "TEI", "models": [{"name": TEI_MODEL, "type": "rerank"}]})
    seed("PATCH", "/api/v1/models/default", {"chat": live_env.chat_id, "embedding": live_env.embed_id})
    browser.navigate(f"{ORIGIN}/datasets")
    _wait_testid(browser, "dataset-create")
    _press(browser, "dataset-create")
    _wait_testid(browser, "field-dataset-name")
    _type_into(browser, "field-dataset-name", unique_name("Core PDF"))
    _press(browser, "create-dataset-submit")
    browser.wait_for("location.pathname === '/dataset/files' && location.search.startsWith('?id=')", "created dataset", timeout=60)
    dataset_id = browser.evaluate("new URLSearchParams(location.search).get('id')")
    with tempfile.TemporaryDirectory(prefix="devrag-core-") as folder:
        path = Path(folder)/"planted-core.pdf"
        path.write_bytes(planted_pdf())
        _upload_through_dialog(browser, str(path), 1, timeout=60)
        _close_upload_dialog(browser)
    _wait_testid(browser, "document-parse")
    _press(browser, "document-parse")
    browser.wait_for(f"{_by_id('document-status')}?.textContent.trim() === 'Finished'", "PDF parsed", timeout=300)
    browser.navigate(f"{ORIGIN}/chats")
    _wait_testid(browser, "rail-assistant-new")
    _press(browser, "rail-assistant-new")
    _wait_testid(browser, "field-assistant-name")
    _type_into(browser, "field-assistant-name", unique_name("Core assistant"))
    choose(browser, "field-assistant-model", live_env.chat_id)
    choose(browser, "field-assistant-rerank", f"{TEI_MODEL}@TEI")
    option = f"document.querySelector('[data-testid=\"assistant-dataset-option\"][data-dataset-id=\"{dataset_id}\"]')"
    _press_expr(browser, option, "the planted dataset")
    _press(browser, "assistant-submit")
    _wait_testid(browser, "chat-input")
    chat_id = browser.evaluate("new URLSearchParams(location.search).get('chat')")
    seed("PUT", f"/api/v1/chats/{chat_id}", {"llm_setting": {"temperature": 0}})
    browser.evaluate(
        "(() => { window.__answerLengths=[]; const note=()=>{"
        " const e=document.querySelector('[data-testid=\"message-assistant\"][aria-busy=\"true\"]');"
        " const n=e?.querySelector(':scope > div:last-child > div')?.textContent.length || 0;"
        " if(n && !window.__answerLengths.includes(n)) window.__answerLengths.push(n); };"
        " new MutationObserver(note).observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true}); })()"
    )
    question_started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    query_before = usage_count("app", question_started, owner.tenant_id, live_env.embed_model)
    question(browser, PDF_FACTS[1].question)
    completed(browser)
    lengths = browser.evaluate("window.__answerLengths")
    assert len(lengths) >= 2 and max(lengths) > min(lengths)
    saved_answer = answer_text(browser)
    assert "52" in saved_answer
    open_first_citation(browser)
    passage = browser.evaluate(f"{_by_id('source-passage')}.textContent")
    assert PDF_FACTS[1].token in passage and "52" in passage
    pill = browser.evaluate(f"{_by_id('cite-pill')}.getAttribute('data-cite-index')")
    browser.wait_for(f"{_by_id('preview-image')}?.complete && {_by_id('preview-image')}?.naturalWidth > 0 && {_by_id('preview-box')} !== null", "PDF image and highlight", timeout=60)
    _assert_box_inside_image(browser)
    shot = SCREENSHOT_DIR/"phase5-core-source.png"
    browser.screenshot(str(shot))
    address = browser.evaluate("location.href")
    browser.navigate(address)
    _wait_testid(browser, "cite-pill")
    assert answer_text(browser) == saved_answer
    open_first_citation(browser)
    assert browser.evaluate(f"{_by_id('source-passage')}.textContent") == passage
    assert browser.evaluate(f"{_by_id('cite-pill')}.getAttribute('data-cite-index')") == pill
    session_id = browser.evaluate("new URLSearchParams(location.search).get('session')")
    stored = api(stack_ready, "GET", f"/api/v1/chats/{chat_id}/sessions/{session_id}", token).json()["data"]
    assert sum(m["role"] == "assistant" and bool(m.get("usage")) and not m.get("empty") for m in stored["messages"]) == 1
    query_count = usage_count("app", question_started, owner.tenant_id, live_env.embed_model) - query_before
    assert 1 <= query_count <= 2  # Question embedding plus at most one citation fallback.
    assert STATE.get("query_embeddings", 0) + query_count <= QUERY_EMBED_CAP
    print("CORE-GATE-EVIDENCE", json.dumps({"query_embeddings": query_count,"stream_lengths": lengths, "pill_index": pill, "screenshot": str(shot), "chat_turns": 1, "provider_save_chat": 1}))
