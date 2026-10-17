"""Page images, the original file and the text preview end to end on the running stack (plan 04-20).

DOC-21, PARSE-03, UI-16, UI-19, T-04-20-01, T-04-20-02. Nothing of devRag is replaced; the files are uploaded through the real route.
"""
from __future__ import annotations

import io
import re
from collections.abc import Iterator
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.helpers.ingest import make_docx, make_html, text_pdf, thirteen_page_pdf, upload_text
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import NOT_FOUND, TOKENS, _bearer, api, join, ok

pytestmark = pytest.mark.e2e

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture(scope="module")
def fake() -> Iterator[FakeProvider]:
    with running_stack_fake_provider() as provider:
        yield provider


@pytest.fixture(scope="module")
def registry(ingress: httpx.Client) -> Iterator[AccountRegistry]:
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        accounts.cleanup()


@pytest.fixture(scope="module")
def owner(ingress: httpx.Client, registry: AccountRegistry, fake: FakeProvider) -> Account:
    return workspace(ingress, registry, fake, "pages")


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(scope="module")
def shelf(ingress: httpx.Client, owner: Account) -> SimpleNamespace:
    dataset_id = ok(create(ingress, owner))["id"]

    def put(name: str, data: bytes, mime: str) -> str:
        return upload_text(ingress, owner, dataset_id, data, name, mime=mime)["id"]

    long_text = ("a" * 300_000).encode()
    return SimpleNamespace(
        dataset_id=dataset_id,
        pdf=put("thirteen.pdf", thirteen_page_pdf(), "application/pdf"),
        blank=put("blank.pdf", text_pdf([None, None]), "application/pdf"),
        txt=put("note.txt", b"hello world", "text/plain"),
        long=put("long.txt", long_text, "text/plain"),
        png=put("pic.png", png_bytes(), "image/png"),
        docx=put('we"ird\r\nname.docx', make_docx(["body"]), DOCX),
        html=put("page.html", make_html("<p>hello</p><script>alert(1)</script>"), "text/html"),
        pdf_bytes=thirteen_page_pdf(),
    )


def image_path(dataset_id: str, doc_id: str, n: object) -> str:
    return f"/api/v1/datasets/{dataset_id}/documents/{doc_id}/pages/{n}/image"


def content_path(dataset_id: str, doc_id: str) -> str:
    return f"/api/v1/datasets/{dataset_id}/documents/{doc_id}/content"


def test_pages_come_back_as_jpegs_of_the_displayed_size(ingress: httpx.Client, owner: Account, shelf: SimpleNamespace) -> None:
    for n in (1, 13):
        resp = api(ingress, "GET", image_path(shelf.dataset_id, shelf.pdf, n), owner.token)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
        assert resp.headers["cache-control"].startswith("private")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert Image.open(io.BytesIO(resp.content)).size == (1785, 2526)
    assert api(ingress, "GET", image_path(shelf.dataset_id, shelf.pdf, 14), owner.token).json() == NOT_FOUND


def test_a_matching_etag_is_answered_with_304(ingress: httpx.Client, owner: Account, shelf: SimpleNamespace) -> None:
    first = api(ingress, "GET", image_path(shelf.dataset_id, shelf.pdf, 2), owner.token)
    etag = first.headers["etag"]
    ingress.cookies.clear()
    again = ingress.get(image_path(shelf.dataset_id, shelf.pdf, 2), headers={**_bearer(owner.token), "If-None-Match": etag}, timeout=60.0)
    assert again.status_code == 304
    assert again.content == b""


def test_a_pdf_without_a_text_layer_still_renders(ingress: httpx.Client, owner: Account, shelf: SimpleNamespace) -> None:
    resp = api(ingress, "GET", image_path(shelf.dataset_id, shelf.blank, 2), owner.token)
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/jpeg"


def test_a_text_document_has_no_page_image(ingress: httpx.Client, owner: Account, shelf: SimpleNamespace) -> None:
    resp = api(ingress, "GET", image_path(shelf.dataset_id, shelf.txt, 1), owner.token)
    assert resp.status_code == 404 and resp.json() == NOT_FOUND


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "99999999999999999999"])
def test_a_malformed_page_number_is_not_found(ingress: httpx.Client, owner: Account, shelf: SimpleNamespace, bad: str) -> None:
    resp = api(ingress, "GET", image_path(shelf.dataset_id, shelf.pdf, bad), owner.token)
    assert resp.status_code == 404 and resp.json() == NOT_FOUND


def test_the_pdf_comes_back_byte_for_byte_and_inline(ingress: httpx.Client, owner: Account, shelf: SimpleNamespace) -> None:
    resp = api(ingress, "GET", content_path(shelf.dataset_id, shelf.pdf), owner.token)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == shelf.pdf_bytes
    assert resp.headers["content-disposition"].startswith("inline")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["content-security-policy"] == "sandbox"
    assert resp.headers["content-length"] == str(len(shelf.pdf_bytes))


def test_a_png_is_served_as_image_png(ingress: httpx.Client, owner: Account, shelf: SimpleNamespace) -> None:
    resp = api(ingress, "GET", content_path(shelf.dataset_id, shelf.png), owner.token)
    assert resp.headers["content-type"] == "image/png" and resp.content == png_bytes()


def test_a_docx_is_an_attachment_with_a_sanitized_name(ingress: httpx.Client, owner: Account, shelf: SimpleNamespace) -> None:
    resp = api(ingress, "GET", content_path(shelf.dataset_id, shelf.docx), owner.token)
    assert resp.status_code == 200
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment")
    assert "\r" not in disposition and "\n" not in disposition
    assert re.search(r'filename="[^"\\]*"', disposition)
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_html_is_never_served_as_text_html(ingress: httpx.Client, owner: Account, shelf: SimpleNamespace) -> None:
    resp = api(ingress, "GET", content_path(shelf.dataset_id, shelf.html), owner.token)
    assert resp.status_code == 200
    assert "text/html" not in resp.headers["content-type"].lower()
    assert resp.headers["content-disposition"].startswith("attachment")
    assert resp.headers["content-security-policy"] == "sandbox"
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_a_text_preview_is_cut_and_other_types_are_refused(ingress: httpx.Client, owner: Account, shelf: SimpleNamespace) -> None:
    short = ok(api(ingress, "GET", content_path(shelf.dataset_id, shelf.txt), owner.token, params={"format": "text"}))
    assert short == {"text": "hello world", "cut": False}
    long = ok(api(ingress, "GET", content_path(shelf.dataset_id, shelf.long), owner.token, params={"format": "text"}))
    assert long["cut"] is True and len(long["text"]) == 262144
    refused = api(ingress, "GET", content_path(shelf.dataset_id, shelf.pdf), owner.token, params={"format": "text"})
    assert refused.status_code == 400
    assert (refused.json().get("data") or {}).get("reason") == "preview_unavailable"
    assert api(ingress, "GET", content_path(shelf.dataset_id, shelf.pdf), owner.token, params={"format": "bogus"}).status_code == 400


def test_an_api_token_and_a_member_can_read(ingress: httpx.Client, registry: AccountRegistry, owner: Account, shelf: SimpleNamespace) -> None:
    ingress.cookies.clear()
    created = ingress.post(TOKENS, headers=_bearer(owner.token))
    assert created.status_code == 200, created.text
    holder = Account(owner.email, owner.password, owner.nickname, owner.user_id, owner.tenant_id, created.json()["data"]["token"])
    assert api(ingress, "GET", image_path(shelf.dataset_id, shelf.pdf, 1), holder.token).status_code == 200
    member = registry.register(prefix="pagesmem")
    join(ingress, owner, member)
    team = ok(create(ingress, owner, permission="team"))["id"]
    doc = upload_text(ingress, owner, team, thirteen_page_pdf(), "team.pdf", mime="application/pdf")["id"]
    assert api(ingress, "GET", image_path(team, doc, 1), member.token).status_code == 200
    assert api(ingress, "GET", content_path(team, doc), member.token).status_code == 200


def test_a_private_dataset_and_another_tenant_get_the_one_404(ingress: httpx.Client, registry: AccountRegistry, owner: Account, fake: FakeProvider) -> None:
    member = registry.register(prefix="pagespriv")
    join(ingress, owner, member)
    private = ok(create(ingress, owner, permission="me"))["id"]
    doc = upload_text(ingress, owner, private, thirteen_page_pdf(), "mine.pdf", mime="application/pdf")["id"]
    stranger = workspace(ingress, registry, fake, "pagesout")
    absent = "0" * 32
    for who in (member, stranger):
        for path in (image_path(private, doc, 1), content_path(private, doc)):
            resp = api(ingress, "GET", path, who.token)
            assert resp.status_code == 404 and resp.json() == NOT_FOUND, (who.email, path)
    assert api(ingress, "GET", image_path(private, absent, 1), owner.token).json() == NOT_FOUND
    assert api(ingress, "GET", image_path(private, doc, 1), owner.token).status_code == 200
