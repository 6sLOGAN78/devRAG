"""A real headless Chrome executes the SPA behind the auth guard (UI-01, UI-02, UI-03, UI-04, UI-07).

The browser is driven over the DevTools pipe by ``test.helpers.chrome_cdp`` (standard library only).
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry, delete_accounts, unique_email, unique_name
from test.helpers.chrome_cdp import ChromeSession, chrome_path
from test.helpers.fake_provider import FakeProvider, fake_provider_stack  # noqa: F401  (fixture)
from test.helpers.uploads import sql, tenant_object_keys, text_bytes
from test.testcases.conftest import BASE_URL, HTTP_PORT
from test.testcases.test_dataset_flow import DATASETS, EMBED_ID, create, workspace
from test.testcases.test_dataset_lifecycle_flow import chunk_count, raw_es  # noqa: F401  (raw_es is a fixture)
from test.testcases.test_provider_flow import api, ok, registry  # noqa: F401  (registry is a fixture)

pytestmark = pytest.mark.e2e

ORIGIN = f"http://127.0.0.1:{HTTP_PORT}"
TOKEN_KEY = "Authorization"  # web/src/utils/authorization.ts


@pytest.fixture
def browser() -> Iterator[ChromeSession]:
    assert chrome_path(), "google-chrome is not installed; see BLOCKERS (browser check not run)"
    with ChromeSession() as session:
        yield session


def _store_token(browser: ChromeSession, token: str) -> None:
    """Set the stored token on the app origin (the same origin the SPA reads), then leave a neutral page."""
    browser.navigate(f"{ORIGIN}/health")
    browser.evaluate(f"localStorage.setItem({json.dumps(TOKEN_KEY)}, {json.dumps(token)})")


def _wait_healthy_cards(browser: ChromeSession) -> None:
    browser.wait_for(
        "document.querySelector('[data-testid=\"status-card-go\"]') !== null"
        " && document.querySelector('[data-testid=\"status-card-python\"]') !== null"
        " && document.documentElement.outerHTML.split('Healthy').length - 1 >= 2",
        "both status cards rendered as Healthy behind the guard",
        timeout=60,
    )


def test_status_page_renders_healthy_cards_in_real_browser(stack_ready: object, account: Account, browser: ChromeSession) -> None:
    _store_token(browser, account.token)
    browser.navigate(f"{ORIGIN}/system-status")
    _wait_healthy_cards(browser)
    dom = browser.evaluate("document.documentElement.outerHTML")
    assert 'data-testid="status-card-go"' in dom, dom[:500]
    assert 'data-testid="status-card-python"' in dom
    assert dom.count("Healthy") >= 2
    assert browser.evaluate("location.pathname") == "/system-status"  # recovered the session, no redirect
    # The signed-in shell carries the account menu and the captioned nav group (plan 02-28).
    assert browser.evaluate("document.querySelector('[data-testid=\"user-menu\"]') !== null") is True
    assert browser.evaluate("document.querySelector('[data-testid=\"nav-item-system-status\"]') !== null") is True


@pytest.fixture
def signout_account(stack_ready: object) -> Iterator[Account]:
    """Sign out ends the shared token for the whole account (D-10), so it must not use the session-wide account."""
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts.register(prefix="signout")
    finally:
        accounts.cleanup()


def test_sign_out_from_the_account_menu_lands_on_a_bare_login_in_real_browser(
    stack_ready: object, signout_account: Account, browser: ChromeSession
) -> None:
    _store_token(browser, signout_account.token)
    browser.navigate(f"{ORIGIN}/system-status")
    _wait_healthy_cards(browser)
    browser.evaluate("document.querySelector('[data-testid=\"user-menu\"]').focus()")
    for event_type in ("keyDown", "keyUp"):
        browser.call(
            "Input.dispatchKeyEvent",
            {"type": event_type, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, **({"text": "\r"} if event_type == "keyDown" else {})},
        )
    browser.wait_for("document.querySelector('[data-testid=\"user-menu-signout\"]') !== null", "account menu opened by keyboard")
    browser.evaluate("document.querySelector('[data-testid=\"user-menu-signout\"]').click()")
    browser.wait_for("location.pathname === '/login'", "sign out lands on /login")
    assert browser.evaluate("location.search") == ""
    assert browser.evaluate(f"localStorage.getItem({json.dumps(TOKEN_KEY)})") is None
    assert browser.evaluate("document.querySelector('[data-testid=\"user-menu\"]') === null") is True


def test_root_redirects_a_signed_in_visitor_to_home_in_real_browser(
    stack_ready: object, account: Account, browser: ChromeSession
) -> None:
    _store_token(browser, account.token)
    browser.navigate(f"{ORIGIN}/")
    browser.wait_for("document.querySelector('[data-testid=\"home-page\"]') !== null", "the home dashboard rendered behind the guard", timeout=60)
    assert browser.evaluate("location.pathname") == "/home"
    assert browser.evaluate("document.querySelector('[data-testid=\"stat-role\"]') !== null") is True


def test_root_redirects_a_signed_out_visitor_to_login_in_real_browser(stack_ready: object, browser: ChromeSession) -> None:
    browser.navigate(f"{ORIGIN}/")
    browser.wait_for("location.pathname.startsWith('/login')", "redirect to /login for a signed-out visitor at /")
    assert browser.evaluate("location.pathname") == "/login"
    assert browser.evaluate("location.search") == ""
    assert browser.evaluate("document.querySelector('[data-testid=\"status-card-go\"]') === null") is True


def test_signed_out_visitor_is_redirected_to_login_in_real_browser(stack_ready: object, browser: ChromeSession) -> None:
    browser.navigate(f"{ORIGIN}/system-status")
    browser.wait_for("location.pathname.startsWith('/login')", "redirect to /login for a signed-out visitor")
    assert browser.evaluate("location.pathname") == "/login"
    assert browser.evaluate("location.search") == "?next=%2Fsystem-status"
    assert browser.evaluate("document.querySelector('[data-testid=\"status-card-go\"]') === null") is True
    assert browser.evaluate(f"localStorage.getItem({json.dumps(TOKEN_KEY)})") is None


def test_rejected_token_is_purged_and_redirects_without_a_reload(stack_ready: object, browser: ChromeSession) -> None:
    _store_token(browser, "not-a-valid-token")
    browser.navigate(f"{ORIGIN}/system-status")
    browser.wait_for("location.pathname.startsWith('/login')", "redirect to /login after the server rejects the token")
    assert browser.evaluate("location.search") == "?next=%2Fsystem-status"
    assert browser.evaluate(f"localStorage.getItem({json.dumps(TOKEN_KEY)})") is None
    assert browser.evaluate("document.querySelector('[data-testid=\"status-card-go\"]') === null") is True


def _type_into(browser: ChromeSession, test_id: str, text: str) -> None:
    """Focus the field and insert the text the way the browser's own input method does (fires real input events)."""
    browser.evaluate(f"document.querySelector('[data-testid=\"{test_id}\"]').focus()")
    browser.call("Input.insertText", {"text": text})


def test_register_land_on_home_reload_and_guard_in_real_browser(stack_ready: object, browser: ChromeSession) -> None:
    """Success criterion 1 in a real Chrome: sign up in the SPA, land on /home, survive a reload, get redirected when signed out."""
    email, nickname, password = unique_email("webreg"), unique_name("nick"), "test-only-pass-0001"
    created: list[Account] = []
    try:
        browser.navigate(f"{ORIGIN}/login?mode=register")
        browser.wait_for("document.querySelector('[data-testid=\"register-form\"]') !== null", "the register form (registration enabled)", timeout=60)
        assert browser.evaluate("document.activeElement && document.activeElement.getAttribute('data-testid')") == "field-nickname"
        _type_into(browser, "field-nickname", nickname)
        _type_into(browser, "field-email", email)
        _type_into(browser, "field-password", password)
        browser.evaluate("document.querySelector('[data-testid=\"register-submit\"]').click()")
        browser.wait_for("location.pathname === '/home'", "registration lands on /home", timeout=60)
        title = f"Welcome, {nickname}"
        browser.wait_for(f"document.querySelector('h1') && document.querySelector('h1').textContent === {json.dumps(title)}", "the welcome title", timeout=60)
        assert browser.evaluate("document.querySelector('[data-testid=\"stat-role\"]').textContent.includes('Owner')") is True
        token = browser.evaluate(f"localStorage.getItem({json.dumps(TOKEN_KEY)})")
        assert token
        info = httpx.get(f"{BASE_URL}/v1/user/info", headers={"Authorization": f"Bearer {token}"}, timeout=10.0).json()["data"]
        created.append(Account(email=email, password=password, nickname=nickname, user_id=info["id"], tenant_id=info["tenant_id"], token=token))
        # The password is nowhere in the page URL or in browser storage.
        assert password not in browser.evaluate("location.href")
        assert password not in browser.evaluate("JSON.stringify(Object.entries(localStorage)) + JSON.stringify(Object.entries(sessionStorage))")

        browser.navigate(f"{ORIGIN}/home")  # a reload: new page load, same storage
        browser.wait_for(f"document.querySelector('h1') && document.querySelector('h1').textContent === {json.dumps(title)}", "welcome title after reload", timeout=60)
        assert browser.evaluate("location.pathname") == "/home"

        browser.evaluate("localStorage.clear()")
        browser.navigate(f"{ORIGIN}/home")
        browser.wait_for("location.pathname === '/login'", "guard redirect after clearing storage", timeout=60)
        assert browser.evaluate("location.search") == "?next=%2Fhome"
        browser.wait_for("document.querySelector('[data-testid=\"login-form\"]') !== null", "sign-in form")
        _type_into(browser, "field-email", email)
        _type_into(browser, "field-password", "not-the-password")
        browser.evaluate("document.querySelector('[data-testid=\"login-submit\"]').click()")
        browser.wait_for("document.querySelector('[data-testid=\"login-error\"]') !== null", "inline sign-in error", timeout=60)
        assert browser.evaluate("document.querySelector('[data-testid=\"login-error\"]').textContent") == "Email or password is incorrect"
        assert browser.evaluate("document.querySelector('[data-sonner-toast]') === null") is True
        assert browser.evaluate("location.pathname") == "/login"
    finally:
        delete_accounts(created)


# --- datasets and uploads in a real Chrome (plan 03-26: UI-10, UI-11, UI-12, E2E-03, E2E-04, DOC-15, KB-07) ---------------------------------


def _by_id(test_id: str) -> str:
    return f"document.querySelector('[data-testid=\"{test_id}\"]')"


def _set_viewport(browser: ChromeSession) -> None:
    """A desktop-sized window: headless Chrome's default layout viewport is smaller than the dialogs' centred position, which puts buttons off-screen."""
    browser.call("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False})


def _wait_testid(browser: ChromeSession, test_id: str, timeout: float = 60.0) -> None:
    browser.wait_for(f"{_by_id(test_id)} !== null", f"the element {test_id}", timeout=timeout)


def _press(browser: ChromeSession, test_id: str) -> None:
    """Click the element with a real mouse press at its centre (fires pointer events, which Radix menus listen for)."""
    # A dialog or menu that is still animating in has not reached its place: a press at the measured centre would miss.
    browser.wait_for("document.getAnimations().every(a => a.playState !== 'running')", f"animations to settle before pressing {test_id}", timeout=10)
    box = browser.evaluate(
        f"(() => {{ const e = {_by_id(test_id)}; e.scrollIntoView({{block: 'center'}}); const r = e.getBoundingClientRect();"
        " return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()"
    )
    point = {"x": box["x"], "y": box["y"], "button": "left", "clickCount": 1}
    browser.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": point["x"], "y": point["y"]})
    browser.call("Input.dispatchMouseEvent", {"type": "mousePressed", **point})
    browser.call("Input.dispatchMouseEvent", {"type": "mouseReleased", **point})


def _text_of(browser: ChromeSession, test_id: str) -> str:
    return str(browser.evaluate(f"({_by_id(test_id)} || {{textContent: ''}}).textContent"))


def _upload_through_dialog(browser: ChromeSession, path: str, expected_rows: int, *, timeout: float) -> float:
    """Open the upload dialog, attach the file to the real input, press Upload and wait for 'Uploaded'. Returns the seconds the upload took."""
    _wait_testid(browser, "dataset-upload")
    _press(browser, "dataset-upload")
    _wait_testid(browser, "upload-input")
    browser.set_file_input('[data-testid="upload-input"]', [path])
    browser.wait_for(f"document.querySelectorAll('[data-testid=\"upload-row\"]').length === {expected_rows}", "the file queued in the dialog")
    browser.wait_for(f"{_by_id('upload-submit')}.textContent === 'Upload {expected_rows} file'", "the Upload button naming the file")
    started = time.monotonic()
    _press(browser, "upload-submit")
    try:
        browser.wait_for(
            "(() => { const s = document.querySelectorAll('[data-testid=\"upload-row-state\"]');"
            " return s.length > 0 && Array.from(s).every(e => e.textContent.startsWith('Uploaded')); })()",
            "every upload row reading Uploaded",
            timeout=timeout,
        )
    except TimeoutError as exc:
        seen = browser.evaluate("(document.querySelector('[data-testid=\"upload-dialog\"]') || document.body).innerText.slice(0, 600)")
        raise AssertionError(f"the upload did not finish; the page showed: {seen!r}") from exc
    return time.monotonic() - started


def _close_upload_dialog(browser: ChromeSession) -> None:
    _press(browser, "upload-close")
    browser.wait_for(f"{_by_id('upload-dialog')} === null", "the upload dialog closed")


def _sign_in_to_dataset_page(browser: ChromeSession, owner: Account, dataset_id: str) -> None:
    _set_viewport(browser)
    _store_token(browser, owner.token)
    browser.navigate(f"{ORIGIN}/dataset/files?id={dataset_id}")
    _wait_testid(browser, "dataset-page")


def test_a_real_browser_creates_a_dataset_uploads_through_the_real_input_and_the_blob_is_stored(
    stack_ready: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider, browser: ChromeSession  # noqa: F811
) -> None:
    owner = workspace(stack_ready, registry, fake_provider_stack, "webds")
    name = unique_name("Chrome dataset")
    with tempfile.TemporaryDirectory(prefix="devrag-upload-") as folder:
        small = Path(folder) / "chrome-note.txt"
        small.write_bytes(text_bytes("browser journey"))
        _set_viewport(browser)
        _store_token(browser, owner.token)
        browser.navigate(f"{ORIGIN}/datasets")
        _wait_testid(browser, "dataset-create")
        _press(browser, "dataset-create")
        _wait_testid(browser, "create-dataset-form")
        _type_into(browser, "field-dataset-name", name)
        _press(browser, "create-dataset-submit")
        browser.wait_for("location.pathname === '/dataset/files' && location.search.startsWith('?id=')", "navigation to the new dataset", timeout=60)
        dataset_id = str(browser.evaluate("new URLSearchParams(location.search).get('id')"))
        assert len(dataset_id) == 32
        _wait_testid(browser, "dataset-page")

        _upload_through_dialog(browser, str(small), 1, timeout=60)
        assert "chrome-note.txt" in browser.evaluate("document.body.innerText")
        _close_upload_dialog(browser)
        browser.wait_for("document.querySelectorAll('[data-testid=\"document-row\"]').length === 1", "the document in the table", timeout=60)
        assert _text_of(browser, "document-status").strip() == "Not started"
        assert _text_of(browser, "document-progress").strip() == "0%"

    listed = ok(api(stack_ready, "GET", f"{DATASETS}/{dataset_id}/documents", owner.token))
    assert listed["total"] == 1 and listed["items"][0]["name"] == "chrome-note.txt"
    assert listed["items"][0]["run"] == "0" and listed["items"][0]["progress"] == 0
    rows = sql("SELECT `run`, `progress`, `name` FROM `document` WHERE `kb_id` = %s", (dataset_id,))
    assert [(r[0], float(r[1]), r[2]) for r in rows] == [("0", 0.0, "chrome-note.txt")]
    keys = tenant_object_keys(owner.tenant_id)
    assert len(keys) == 1 and keys[0].startswith(f"{owner.tenant_id}/") and len(keys[0].split("/", 1)[1]) == 32, keys
    assert fake_provider_stack.hits("/v1/embeddings"), "the dataset's embedding model was tested through the fake provider, not a real one"


def test_a_slow_large_upload_outlives_the_default_timeout_and_the_delete_removes_everything(
    stack_ready: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider, raw_es: object, browser: ChromeSession  # noqa: F811
) -> None:
    owner = workspace(stack_ready, registry, fake_provider_stack, "webbig")
    dataset = ok(create(stack_ready, owner, unique_name("Large upload")))
    dataset_id = str(dataset["id"])
    assert dataset["embd_id"] == EMBED_ID
    with tempfile.TemporaryDirectory(prefix="devrag-upload-") as folder:
        big = Path(folder) / "twelve-mebibytes.txt"
        with big.open("wb") as handle:
            block = text_bytes("large", 1 << 20)
            for _ in range(12):
                handle.write(block)
        assert big.stat().st_size == 12 * 1024 * 1024
        _sign_in_to_dataset_page(browser, owner, dataset_id)
        try:
            browser.throttle_upload(1_048_576)
            elapsed = _upload_through_dialog(browser, str(big), 1, timeout=90)
        finally:
            browser.throttle_upload(None)
        assert elapsed > 10, f"the upload took {elapsed:.1f}s; a throttle that does not slow the upload proves nothing about the 10 s client timeout"
        assert "The connection was lost" not in browser.evaluate("document.body.innerText")
        assert _text_of(browser, "upload-row-state").startswith("Uploaded")
        _close_upload_dialog(browser)
        browser.wait_for("document.querySelectorAll('[data-testid=\"document-row\"]').length === 1", "the large document in the table", timeout=60)
        assert _text_of(browser, "document-status").strip() == "Not started"
        browser.wait_for("document.querySelector('[data-testid=\"dataset-meta\"]').textContent.includes('1 document')", "the meta line counting the document", timeout=60)
        assert len(tenant_object_keys(owner.tenant_id)) == 1
        assert os.path.getsize(big) == 12 * 1024 * 1024

    # Delete the dataset through the dialog after reading the count it states.
    _press(browser, "dataset-actions")
    _wait_testid(browser, "dataset-menu-delete")
    _press(browser, "dataset-menu-delete")
    browser.wait_for(
        "(document.querySelector('[data-testid=\"dataset-delete-count\"]') || {textContent: ''})"
        ".textContent.includes('and its 1 document will be permanently deleted')",
        "the delete dialog stating the count",
        timeout=60,
    )
    _press(browser, "dataset-delete-confirm")
    browser.wait_for("location.pathname === '/datasets'", "the gallery after the delete", timeout=90)
    assert tenant_object_keys(owner.tenant_id) == [], "the blob left storage"
    assert sql("SELECT COUNT(*) FROM `knowledgebase` WHERE `tenant_id` = %s", (owner.tenant_id,))[0][0] == 0
    assert sql("SELECT COUNT(*) FROM `document` WHERE `kb_id` = %s", (dataset_id,))[0][0] == 0
    assert chunk_count(raw_es, owner.tenant_id, dataset_id) == 0  # type: ignore[arg-type]
