"""Sharing policy through the real SPA, API and databases; the model provider is local."""
# ruff: noqa: F811
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from test.helpers.accounts import unique_name
from test.helpers.ingest import start_parse, upload_text, wait_run
from test.helpers.planted import FACTS, planted_txt
from test.testcases.test_chat_assistant_flow import fake, made, read, registry, team  # noqa: F401
from test.testcases.test_chat_flow import ask
from test.testcases.test_provider_flow import api, ok
from test.testcases.test_spa_browser import _by_id, _store_token, _type_into, _wait_testid
from test.testcases.test_spa_chat_browser import completed, question
from test.testcases.test_spa_ingestion_browser import (
    ORIGIN,
    _press,
    _press_expr,
    browser,  # noqa: F401
)

pytestmark = pytest.mark.e2e


@pytest.fixture
def shared(ingress, team, fake):
    doc = upload_text(ingress, team.a, team.team_dataset, planted_txt(), unique_name("sharing") + ".txt")
    assert start_parse(ingress, team.a, team.team_dataset, [doc["id"]]).status_code == 200
    wait_run(ingress, team.a, team.team_dataset, doc["id"], "3", timeout=180)
    common = {"kb_ids": [team.team_dataset], "vector_similarity_weight": 0, "similarity_threshold": 0.2}
    public = made(ingress, team, team.a, name=unique_name("Shared"), permission="team", **common)
    private = made(ingress, team, team.a, name=unique_name("Private"), **common)
    fake.chat_mode = "marker"
    return SimpleNamespace(team=team, public=public, private=private, fake=fake, ingress=ingress)


def open_as(browser, world, who, chat=None, session=None):
    _store_token(browser, who.token)
    entry = json.dumps({"userId": who.user_id, "tenantId": world.team.owner.tenant_id})
    browser.evaluate(f"localStorage.setItem('devrag.workspace', {json.dumps(entry)})")
    query = f"?chat={chat}" if chat else ""
    if session:
        query += f"&session={session}"
    browser.navigate(f"{ORIGIN}/chats{query}")
    _wait_testid(browser, "chat-page")
    browser.wait_for("document.querySelector('[data-testid=\"rail-assistant-row\"]') !== null", "shared assistant rail", timeout=60)
    if chat:
        _wait_testid(browser, "chat-header")


def listed(browser):
    return browser.evaluate("[...document.querySelectorAll('[data-testid=\"rail-assistant-row\"]')].map(e=>e.getAttribute('data-chat-id'))")


def settings(browser):
    _press(browser, "chat-settings")
    _wait_testid(browser, "field-assistant-name")


def only_me(browser):
    _press_expr(browser, f"{_by_id('assistant-visibility-me')}.closest('label')", "Only me")
    _press(browser, "assistant-submit")


def test_teammate_sees_shared_assistant_and_own_empty_chat_list(shared, browser):
    world = shared
    chat_id, private_id = world.public["id"], world.private["id"]
    answer = ok(ask(world.ingress, world.team.a, chat_id, FACTS[0].question))
    assert answer["session_id"]
    for who in (world.team.b, world.team.owner, world.team.admin):
        open_as(browser, world, who, chat_id)
        assert chat_id in listed(browser) and private_id not in listed(browser)
        assert browser.evaluate("document.querySelectorAll('[data-testid=\"rail-chat-row\"]').length") == 0
    open_as(browser, world, world.team.a, chat_id)
    assert {chat_id, private_id} <= set(listed(browser))
    browser.wait_for("document.querySelectorAll('[data-testid=\"rail-chat-row\"]').length === 1", "creator's own chat")


def test_narrowing_is_refused_while_a_teammate_has_chats_then_succeeds(shared, browser):
    world = shared
    chat_id = world.public["id"]
    open_as(browser, world, world.team.b, chat_id)
    question(browser, FACTS[0].question)
    completed(browser)
    session_id = browser.evaluate("new URLSearchParams(location.search).get('session')")
    open_as(browser, world, world.team.a, chat_id)
    settings(browser)
    only_me(browser)
    _wait_testid(browser, "assistant-error")
    assert "1" in browser.evaluate(f"{_by_id('assistant-error')}.textContent")
    assert browser.evaluate("document.querySelector('[role=\"alertdialog\"]') === null") is True
    assert browser.evaluate(f"{_by_id('assistant-visibility-me')}.checked") is True
    assert api(world.ingress, "GET", f"/api/v1/chats/{chat_id}/sessions/{session_id}", world.team.b.token).status_code == 200
    open_as(browser, world, world.team.b, chat_id, session_id)
    _press(browser, "chat-more")
    _wait_testid(browser, "chat-menu-delete-chat")
    _press(browser, "chat-menu-delete-chat")
    _wait_testid(browser, "delete-chat-confirm")
    _press(browser, "delete-chat-confirm")
    browser.wait_for("!new URLSearchParams(location.search).has('session')", "chat deleted")
    open_as(browser, world, world.team.a, chat_id)
    settings(browser)
    only_me(browser)
    browser.wait_for(f"{_by_id('field-assistant-name')} === null", "settings saved")
    browser.wait_for("document.body.innerText.includes('Assistant saved')", "saved notification")
    open_as(browser, world, world.team.b)
    assert chat_id not in listed(browser)


def test_admin_can_edit_a_shared_assistant_and_narrowing_removes_it_from_their_list(shared, browser):
    world = shared
    chat_id = world.public["id"]
    open_as(browser, world, world.team.b, chat_id)
    assert browser.evaluate(f"{_by_id('chat-settings')} === null") is True
    open_as(browser, world, world.team.admin, chat_id)
    settings(browser)
    only_me(browser)
    browser.wait_for(f"{_by_id('field-assistant-name')} === null", "settings close")
    browser.wait_for("document.body.innerText.includes('Only the person who made it')", "creator-only notification")
    browser.wait_for(f"!Array.from(document.querySelectorAll('[data-testid=\"rail-assistant-row\"]')).some(e=>e.dataset.chatId === {json.dumps(chat_id)})", "narrowed assistant leaves admin rail")
    assert world.private["id"] not in listed(browser)


def test_a_dataset_the_editor_cannot_open_stays_linked(shared, browser):
    world = shared
    chat_id = world.public["id"]
    ok(api(world.ingress, "PUT", f"/api/v1/datasets/{world.team.team_dataset}", world.team.a.token, body={"permission": "me"}))
    try:
        open_as(browser, world, world.team.admin, chat_id)
        _wait_testid(browser, "chat-datasets-notice")
        settings(browser)
        _wait_testid(browser, "assistant-datasets-unavailable")
        assert "1" in browser.evaluate(f"{_by_id('assistant-datasets-unavailable')}.textContent")
        assert "stays linked" in browser.evaluate(f"{_by_id('assistant-datasets-unavailable')}.textContent")
        hidden = f"document.querySelector('[data-testid=\"assistant-dataset-option\"][data-dataset-id=\"{world.team.team_dataset}\"]')"
        assert browser.evaluate(f"{hidden} === null") is True
        changed = "Instructions saved while a source is hidden"
        _type_into(browser, "field-assistant-system", changed)
        _press(browser, "assistant-submit")
        browser.wait_for(f"{_by_id('field-assistant-name')} === null", "hidden-link settings saved")
        detail = ok(read(world.ingress, world.team.a, chat_id))
        assert detail["kb_ids"] == [world.team.team_dataset]
        assert changed in detail["prompt_config"]["system"]
        before = len(world.fake.chat_requests())
        question(browser, FACTS[0].question)
        _wait_testid(browser, "chat-send-error")
        assert len(world.fake.chat_requests()) == before
        open_as(browser, world, world.team.a, chat_id)
        assert browser.evaluate(f"{_by_id('chat-datasets-notice')} === null") is True
        question(browser, FACTS[0].question)
        completed(browser)
        _wait_testid(browser, "cite-pill")
    finally:
        ok(api(world.ingress, "PUT", f"/api/v1/datasets/{world.team.team_dataset}", world.team.a.token, body={"permission": "team"}))


def test_deleting_a_shared_assistant_states_the_count_and_removes_every_chat(shared, browser):
    world = shared
    chat_id = world.public["id"]
    final = ok(ask(world.ingress, world.team.b, chat_id, FACTS[0].question))
    open_as(browser, world, world.team.a, chat_id)
    _press(browser, "chat-more")
    _wait_testid(browser, "chat-menu-delete-assistant")
    _press(browser, "chat-menu-delete-assistant")
    _wait_testid(browser, "delete-assistant-body")
    browser.wait_for(f"{_by_id('delete-assistant-body')}.getAttribute('data-count') === '1'", "one affected teammate")
    assert "1 other member" in browser.evaluate(f"{_by_id('delete-assistant-body')}.textContent")
    _press(browser, "delete-assistant-confirm")
    browser.wait_for(f"!Array.from(document.querySelectorAll('[data-testid=\"rail-assistant-row\"]')).some(e=>e.dataset.chatId === {json.dumps(chat_id)})", "assistant deleted")
    assert api(world.ingress, "GET", f"/api/v1/chats/{chat_id}/sessions/{final['session_id']}", world.team.b.token).status_code == 404
    open_as(browser, world, world.team.b)
    assert chat_id not in listed(browser)
