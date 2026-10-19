"""A real headless Chrome walks the Phase 4 screens against the real stack and the real executor container (UI-13, UI-15, UI-16, UI-17, UI-19, E2E-05, E2E-06).

The browser is driven over the DevTools pipe by ``test.helpers.chrome_cdp`` (standard library only), in the 1280 by 900 metrics override, with real
mouse presses that wait for animations to settle (plan 03-26). Only the third-party embedding provider is a loopback fake. Documents are tiny (D-16).
Waiting is ``wait_for`` / ``wait_until`` with deadlines; there are no fixed delays.
"""
from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry, unique_name
from test.helpers.chrome_cdp import ChromeSession, chrome_path
from test.helpers.fake_provider import FakeProvider, fake_provider_stack  # noqa: F401  (fixture)
from test.helpers.ingest import chunk_texts, doc_row, paragraphs, start_parse, upload_text, wait_run
from test.helpers.office_files import make_docx
from test.helpers.pdf_files import thirteen_page_pdf
from test.helpers.wait import wait_until
from test.testcases.conftest import HTTP_PORT
from test.testcases.test_dataset_flow import DATASETS, create, workspace
from test.testcases.test_provider_flow import api, ok, registry  # noqa: F401  (registry is a fixture)
from test.testcases.test_spa_browser import _by_id, _set_viewport, _store_token, _wait_testid

pytestmark = pytest.mark.e2e

ORIGIN = f"http://127.0.0.1:{HTTP_PORT}"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF = "application/pdf"
PDF_CHUNKS = 26  # the offline count of the 13-page PDF at chunk_token_num 25 (04-33, R-182)
PDF_PAGE_WIDTH = 1785  # 595 points rendered at zoom 3
BATCH = 64  # INGEST_BATCH_SIZE of the default executor: chunks are indexed 64 at a time
SCREENSHOT_DIR = Path(os.environ.get("DEVRAG_SCREENSHOT_DIR") or tempfile.gettempdir())


@pytest.fixture
def browser() -> Iterator[ChromeSession]:
    assert chrome_path(), "google-chrome is not installed; see BLOCKERS (browser check not run)"
    with ChromeSession() as session:
        _set_viewport(session)
        yield session


def _press_expr(browser: ChromeSession, element: str, label: str) -> None:
    """A real mouse press at the centre of the element the expression returns, once finite animations have settled (a spinner never does)."""
    settled = "document.getAnimations().every(a => a.playState !== 'running' || a.effect.getComputedTiming().iterations === Infinity)"
    browser.wait_for(settled, f"finite animations to settle before pressing {label}", timeout=10)
    browser.wait_for(f"(() => {{ const e = {element}; return e !== null && e !== undefined; }})()", f"{label} to exist", timeout=30)
    centre = "e.scrollIntoView({block: 'center'}); const r = e.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2};"
    box = browser.evaluate("(() => { const e = " + element + "; " + centre + " })()")
    point = {"x": box["x"], "y": box["y"], "button": "left", "clickCount": 1}
    browser.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": point["x"], "y": point["y"]})
    browser.call("Input.dispatchMouseEvent", {"type": "mousePressed", **point})
    browser.call("Input.dispatchMouseEvent", {"type": "mouseReleased", **point})


def _press(browser: ChromeSession, test_id: str) -> None:
    _press_expr(browser, _by_id(test_id), test_id)


def _card(index: int) -> str:
    return f"document.querySelectorAll('[data-testid=\"chunk-card\"]')[{index}]"


def _in_card(index: int, test_id: str) -> str:
    return f"{_card(index)}.querySelector('[data-testid=\"{test_id}\"]')"


def _label_of(element: str) -> str:
    """Switches and radios are visually hidden inputs; a person presses the label that wraps them."""
    return f"{element}.closest('label')"


def _card_texts(browser: ChromeSession) -> list[str]:
    return list(browser.evaluate("[...document.querySelectorAll('[data-testid=\"chunk-card\"]')].map(c => c.querySelector('[data-testid=\"chunk-text\"]')?.textContent ?? '')"))


def _replace_text(browser: ChromeSession, text: str) -> None:
    """Select everything in the chunk editor and type over it with the browser's own input method."""
    browser.evaluate("(() => { const t = document.querySelector('[data-testid=\"chunk-editor-text\"]'); t.focus(); t.select(); })()")
    browser.call("Input.insertText", {"text": text})
    browser.wait_for(f"document.querySelector('[data-testid=\"chunk-editor-text\"]').value === {json.dumps(text)}", "the typed text in the editor", timeout=10)


class Scene:
    def __init__(self, ingress: httpx.Client, owner: Account, fake: FakeProvider, dataset_id: str) -> None:
        self.ingress, self.owner, self.fake, self.dataset_id = ingress, owner, fake, dataset_id

    def add(self, data: bytes, name: str, mime: str = "text/plain", *, chunk_tokens: int | None = None) -> str:
        doc = upload_text(self.ingress, self.owner, self.dataset_id, data, name, mime=mime)
        if chunk_tokens is not None:
            ok(api(self.ingress, "PATCH", f"{DATASETS}/{self.dataset_id}/documents/{doc['id']}", self.owner.token, body={"parser_config": {"chunk_token_num": chunk_tokens}}))
        return str(doc["id"])

    def parse(self, doc_id: str) -> None:
        assert start_parse(self.ingress, self.owner, self.dataset_id, [doc_id]).status_code == 200
        wait_run(self.ingress, self.owner, self.dataset_id, doc_id, "3", timeout=150)

    def chunk_total(self, doc_id: str) -> int:
        data = ok(api(self.ingress, "GET", f"{DATASETS}/{self.dataset_id}/documents/{doc_id}/chunks", self.owner.token, params={"page": "1", "size": "1"}))
        return int(data["total"])

    def open(self, browser: ChromeSession, path: str, ready_test_id: str) -> None:
        _store_token(browser, self.owner.token)
        browser.navigate(f"{ORIGIN}{path}")
        _wait_testid(browser, ready_test_id)

    def files(self, browser: ChromeSession) -> None:
        self.open(browser, f"/dataset/files?id={self.dataset_id}", "dataset-page")

    def chunks_page(self, browser: ChromeSession, doc_id: str) -> None:
        self.open(browser, f"/chunk?id={self.dataset_id}&doc={doc_id}", "chunk-page")


@pytest.fixture
def scene(stack_ready: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> Iterator[Scene]:  # noqa: F811
    owner = workspace(stack_ready, registry, fake_provider_stack, "webing")
    dataset = ok(create(stack_ready, owner, unique_name("Ingestion journey")))
    yield Scene(stack_ready, owner, fake_provider_stack, str(dataset["id"]))
    fake_provider_stack.delay_ms, fake_provider_stack.embed_mode = 0, "ok"


def test_pressing_parse_on_the_pdf_row_moves_the_badge_to_finished_with_a_chunk_count_and_no_reload(scene: Scene, browser: ChromeSession) -> None:
    scene.add(thirteen_page_pdf(), "thirteen.pdf", PDF, chunk_tokens=25)
    scene.fake.delay_ms = 3000  # long enough for the page's two-second poll to see Parsing
    scene.files(browser)
    browser.wait_for("document.querySelectorAll('[data-testid=\"document-row\"]').length === 1", "the PDF row")
    browser.evaluate(
        "(() => { window.__seen = []; window.__marker = 'kept'; window.__origin = performance.timeOrigin;"
        " const note = () => { const e = document.querySelector('[data-testid=\"document-status\"]'); if (!e) return;"
        " const t = e.textContent.trim(); if (window.__seen[window.__seen.length - 1] !== t) window.__seen.push(t); };"
        " new MutationObserver(note).observe(document.body, {subtree: true, childList: true, characterData: true}); note(); })()"
    )
    _press(browser, "document-parse")
    browser.wait_for("document.querySelector('[data-testid=\"document-status\"]').textContent.trim() === 'Finished'", "the badge reading Finished", timeout=150)
    seen = browser.evaluate("window.__seen")
    assert seen[0] == "Not started" and "Parsing" in seen and seen[-1] == "Finished", seen
    assert seen.index("Parsing") < len(seen) - 1
    assert browser.evaluate("window.__marker") == "kept", "the page was reloaded"
    assert browser.evaluate("performance.timeOrigin === window.__origin") is True
    browser.wait_for(f"document.querySelector('[data-testid=\"document-status-detail\"]').textContent.includes('{PDF_CHUNKS} chunks')", "the chunk count under the badge")
    assert browser.evaluate("document.querySelector('[data-testid=\"document-progress\"]').textContent.includes('100%')") is True


def _inside(browser: ChromeSession) -> dict[str, Any]:
    return browser.evaluate(
        "(() => { const i = document.querySelector('[data-testid=\"preview-image\"]').getBoundingClientRect();"
        " const b = document.querySelector('[data-testid=\"preview-box\"]').getBoundingClientRect();"
        " return {img: [i.left, i.top, i.right, i.bottom], box: [b.left, b.top, b.right, b.bottom]}; })()"
    )


def _assert_box_inside_image(browser: ChromeSession) -> None:
    rects = _inside(browser)
    (il, it, ir, ib), (bl, bt, br, bb) = rects["img"], rects["box"]
    assert br > bl and bb > bt, f"the box has no area: {rects}"
    tolerance = 1.0
    assert bl >= il - tolerance and bt >= it - tolerance and br <= ir + tolerance and bb <= ib + tolerance, f"the box is not inside the image: {rects}"


def test_the_inspector_shows_the_page_image_with_the_chunk_box_inside_it_and_changes_page_with_the_chunk(scene: Scene, browser: ChromeSession) -> None:
    doc_id = scene.add(thirteen_page_pdf(), "thirteen.pdf", PDF, chunk_tokens=25)
    scene.parse(doc_id)
    scene.files(browser)
    _wait_testid(browser, "document-name-link")
    _press(browser, "document-name-link")  # the row link opens the inspector without a reload
    browser.wait_for("location.pathname === '/chunk'", "the inspector route", timeout=30)
    ready = "(() => { const i = document.querySelector('[data-testid=\"preview-image\"]'); return i !== null && i.complete && i.naturalWidth > 0; })()"
    browser.wait_for(ready, "the page image to load", timeout=60)
    assert browser.evaluate("document.querySelector('[data-testid=\"preview-image\"]').naturalWidth") == PDF_PAGE_WIDTH
    assert browser.evaluate("document.querySelector('[data-testid=\"preview-caption\"]').textContent") == "Page 1 of 13"
    first_source = browser.evaluate("document.querySelector('[data-testid=\"preview-image\"]').src")

    _press_expr(browser, _in_card(0, "chunk-select"), "the first chunk's select button")
    browser.wait_for("document.querySelector('[data-testid=\"preview-box\"]') !== null", "the box of the selected chunk")
    _assert_box_inside_image(browser)
    browser.screenshot(str(SCREENSHOT_DIR / "devrag-inspector-box-page1.png"))

    # Page 13 lies on the second list page (26 chunks, 20 to a page).
    _press_expr(browser, "[...document.querySelectorAll('nav[aria-label=\"Chunk pages\"] button')].find(b => b.textContent.trim() === 'Next')", "the Next button of the chunk list")
    on_last = (
        "[...document.querySelectorAll('[data-testid=\"chunk-card\"]')].find(c => [...c.querySelectorAll('[data-testid=\"chunk-page-chip\"]')]"
        ".some(x => x.textContent.trim() === 'Page 13'))"
    )
    browser.wait_for(f"{on_last} !== undefined", "a chunk card with a Page 13 chip", timeout=30)
    _press_expr(browser, f"{on_last}.querySelector('[data-testid=\"chunk-select\"]')", "the Page 13 chunk's select button")
    browser.wait_for("document.querySelector('[data-testid=\"preview-caption\"]').textContent === 'Page 13 of 13'", "the caption to read Page 13 of 13", timeout=30)
    browser.wait_for(f"{ready} && document.querySelector('[data-testid=\"preview-image\"]').src !== {json.dumps(first_source)}", "the image of page 13", timeout=60)
    browser.wait_for("document.querySelector('[data-testid=\"preview-box\"]') !== null", "the box on page 13")
    _assert_box_inside_image(browser)
    browser.screenshot(str(SCREENSHOT_DIR / "devrag-inspector-box-page13.png"))


def test_an_edit_an_added_chunk_and_a_switched_off_chunk_survive_a_reload_and_the_off_filter_lists_the_chunk(scene: Scene, browser: ChromeSession) -> None:
    doc_id = scene.add(paragraphs(3), "notes.txt")
    scene.parse(doc_id)
    scene.chunks_page(browser, doc_id)
    browser.wait_for("document.querySelectorAll('[data-testid=\"chunk-card\"]').length === 3", "three chunk cards", timeout=30)

    edited = "edited in a real browser about quasars"
    _press_expr(browser, _in_card(0, "chunk-edit"), "the pencil of chunk 1")
    _wait_testid(browser, "chunk-editor-text")
    _replace_text(browser, edited)
    _press(browser, "chunk-editor-save")
    browser.wait_for(f"document.querySelector('[data-testid=\"chunk-editor\"]') === null && {_card(0)}.textContent.includes({json.dumps(edited)})", "the edit saved", timeout=60)

    added = "added by hand in a real browser about harbors"
    _press(browser, "chunk-add")
    _wait_testid(browser, "chunk-editor-text")
    _replace_text(browser, added)
    _press(browser, "chunk-editor-save")
    browser.wait_for("document.querySelectorAll('[data-testid=\"chunk-card\"]').length === 4", "the added chunk listed", timeout=60)
    browser.wait_for(f"document.querySelector('[data-testid=\"chunk-editor\"]') === null && {_card(3)}.textContent.includes({json.dumps(added)})", "the added chunk last", timeout=30)

    off_text = _card_texts(browser)[1]
    _press_expr(browser, _label_of(_in_card(1, "chunk-switch")), "the switch of chunk 2")
    browser.wait_for(f"{_in_card(1, 'chunk-badge-off')} !== null", "chunk 2 badged Off", timeout=30)

    scene.chunks_page(browser, doc_id)  # a reload
    browser.wait_for("document.querySelectorAll('[data-testid=\"chunk-card\"]').length === 4", "four chunks after the reload", timeout=30)
    texts = _card_texts(browser)
    assert texts[0] == edited and texts[3] == added, texts
    assert browser.evaluate(f"{_in_card(0, 'chunk-badge-edited')} !== null") is True
    assert browser.evaluate(f"{_in_card(3, 'chunk-badge-manual')} !== null") is True
    assert browser.evaluate(f"{_in_card(1, 'chunk-badge-off')} !== null") is True
    _press_expr(browser, _label_of(_by_id("chunk-filter-off")), "the Off filter")
    browser.wait_for("document.querySelectorAll('[data-testid=\"chunk-card\"]').length === 1", "the Off filter listing one chunk", timeout=30)
    assert _card_texts(browser) == [off_text]


def test_parse_again_states_the_counts_and_replace_brings_back_the_original_count(scene: Scene, browser: ChromeSession) -> None:
    doc_id = scene.add(paragraphs(3), "notes.txt")
    scene.parse(doc_id)
    listed = chunk_texts(api, scene.ingress, scene.owner.token, scene.dataset_id, doc_id)
    path = f"{DATASETS}/{scene.dataset_id}/documents/{doc_id}/chunks"
    ok(api(scene.ingress, "PATCH", f"{path}/{listed[0]['id']}", scene.owner.token, body={"content_with_weight": "edited for the parse again journey"}))
    ok(api(scene.ingress, "POST", path, scene.owner.token, body={"content_with_weight": "added for the parse again journey"}))
    scene.files(browser)
    browser.wait_for("document.querySelector('[data-testid=\"document-status-detail\"]').textContent.includes('4 chunks')", "four chunks under the badge", timeout=30)
    _press(browser, "document-more")
    _wait_testid(browser, "document-menu-reparse")
    _press(browser, "document-menu-reparse")
    _wait_testid(browser, "reparse-dialog")
    count = lambda test_id: browser.evaluate(f"document.querySelector('[data-testid=\"{test_id}\"]').textContent.trim()")  # noqa: E731
    assert (count("reparse-chunks"), count("reparse-edited"), count("reparse-manual")) == ("4", "1", "1")
    _press(browser, "reparse-confirm")
    browser.wait_for(
        "document.querySelector('[data-testid=\"reparse-dialog\"]') === null && document.querySelector('[data-testid=\"document-status\"]').textContent.trim() === 'Finished'"
        " && document.querySelector('[data-testid=\"document-status-detail\"]').textContent.includes('3 chunks')",
        "Finished with the original three chunks",
        timeout=150,
    )
    again = chunk_texts(api, scene.ingress, scene.owner.token, scene.dataset_id, doc_id)
    assert len(again) == 3 and {c["origin"] for c in again} == {"parsed"}


def test_cancelling_a_running_parse_shows_cancelled_or_partly_indexed_and_parse_again_starts_without_a_dialog(scene: Scene, browser: ChromeSession) -> None:
    total = 200
    doc_id = scene.add(paragraphs(total), "cancel.txt")
    scene.fake.delay_ms = 1500
    scene.files(browser)
    browser.wait_for("document.querySelectorAll('[data-testid=\"document-row\"]').length === 1", "the row")
    _press(browser, "document-parse")
    wait_until(lambda: BATCH <= scene.chunk_total(doc_id) < total, timeout=120, interval=0.2, describe=lambda: "chunks to exist while the parse runs")
    _press(browser, "document-cancel")
    browser.wait_for(
        "['Cancelled', 'Partly indexed'].includes(document.querySelector('[data-testid=\"document-status\"]').textContent.trim())",
        "Cancelled or Partly indexed",
        timeout=15,
    )
    scene.fake.delay_ms = 0
    state = {"last": -1, "same": 0}

    def settled() -> bool:
        now = scene.chunk_total(doc_id)
        state["same"] = state["same"] + 1 if now == state["last"] else 0
        state["last"] = now
        return state["same"] >= 3

    wait_until(settled, timeout=60, interval=1.0, describe=lambda: "the chunk count to settle")
    _press(browser, "document-reparse")
    status = "document.querySelector('[data-testid=\"document-status\"]').textContent.trim() === 'Finished'"
    detail = f"document.querySelector('[data-testid=\"document-status-detail\"]').textContent.includes('{total} chunks')"
    browser.wait_for(
        f"{status} && {detail}",
        "Finished with all chunks",
        timeout=150,
    )
    assert browser.evaluate(f"{_by_id('reparse-dialog')} === null") is True, "no dialog was asked for after a cancel with nothing edited"
    assert doc_row(scene.ingress, scene.owner, scene.dataset_id, doc_id)["run"] == "3"


def test_the_viewer_shows_a_pdf_page_and_a_txt_body_and_the_docx_download_saves_a_file(scene: Scene, browser: ChromeSession) -> None:
    pdf_id = scene.add(thirteen_page_pdf(), "thirteen.pdf", PDF)
    txt_id = scene.add(paragraphs(2), "plain.txt")
    docx_bytes = make_docx(["a paragraph for the download journey"])
    docx_id = scene.add(docx_bytes, "report.docx", DOCX)

    scene.open(browser, f"/document?id={scene.dataset_id}&doc={pdf_id}", "viewer-meta")
    browser.wait_for("(() => { const i = document.querySelector('[data-testid=\"preview-image\"]'); return i !== null && i.complete && i.naturalWidth > 0; })()", "the PDF page image", timeout=60)

    scene.open(browser, f"/document?id={scene.dataset_id}&doc={txt_id}", "viewer-meta")
    browser.wait_for("(document.querySelector('[data-testid=\"viewer-text\"]') || {textContent: ''}).textContent.includes('para0000')", "the TXT body", timeout=60)
    assert browser.evaluate("document.querySelector('[data-testid=\"viewer-text\"]').tagName") == "PRE"

    with tempfile.TemporaryDirectory(prefix="devrag-download-") as folder:
        scene.open(browser, f"/document?id={scene.dataset_id}&doc={docx_id}", "viewer-meta")
        browser.allow_downloads(folder)
        _press(browser, "viewer-download")
        wait_until(lambda: "report.docx" in browser.download_names(), timeout=30, interval=0.2, describe=lambda: "a download named report.docx")
        saved = Path(folder)
        wait_until(lambda: any(p.name == "report.docx" for p in saved.iterdir()), timeout=30, interval=0.2, describe=lambda: "report.docx in the download folder")
        assert (saved / "report.docx").read_bytes() == docx_bytes
