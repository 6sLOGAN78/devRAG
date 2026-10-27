"""Document detail, settings change and list rows end to end on the real stack (plan 04-16; DOC-12, DOC-20, DOC-23, CHUNK-02, KB-19, D-02, D-07, D-15, D-27).

Nothing of devRag is replaced: Nginx, the app, the task-executor container, MySQL, MinIO, Valkey and Elasticsearch are the running stack. The
loopback provider is only the third party's end of the embedding wire. Waiting is polling with a deadline.
"""
from __future__ import annotations

import uuid

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider
from test.helpers.ingest import doc_row, index_count, paragraphs, start_parse, upload_text, wait_run
from test.helpers.pdf_files import garbage_bytes, thirteen_page_pdf
from test.testcases.test_dataset_flow import DATASETS, create
from test.testcases.test_parse_flow import fake, owner, registry, settings  # noqa: F401  (fixtures)
from test.testcases.test_provider_flow import NOT_FOUND, TOKENS, _bearer, join, ok

pytestmark = pytest.mark.e2e

FORBIDDEN = {"code": 403, "message": "forbidden", "data": None}
DELIMITER = "\n!?;。；！？"
ROW_BANNED = {"status", "source", "location", "content_hash", "bucket", "key", "chunk_num"}
DETAIL_EXTRA = {"chunk_token_num", "delimiter", "overlapped_percent", "preview"}
LONG = 200


def reason_of(resp: httpx.Response) -> object:
    return (resp.json().get("data") or {}).get("reason")


def new_dataset(ingress: httpx.Client, who: Account, **body: object) -> str:
    return ok(create(ingress, who, **body))["id"]


def path_of(dataset_id: str, doc_id: str) -> str:
    return f"{DATASETS}/{dataset_id}/documents/{doc_id}"


def call(ingress: httpx.Client, method: str, path: str, token: str, body: object = None) -> httpx.Response:
    ingress.cookies.clear()
    resp = ingress.request(method, path, headers=_bearer(token), json=body, timeout=60.0)
    assert resp.headers.get("x-api-source") == "python", (method, path, resp.status_code)
    return resp


def detail(ingress: httpx.Client, who: Account, dataset_id: str, doc_id: str) -> dict:
    return ok(call(ingress, "GET", path_of(dataset_id, doc_id), who.token))


def patch(ingress: httpx.Client, who: Account, dataset_id: str, doc_id: str, body: object) -> httpx.Response:
    return call(ingress, "PATCH", path_of(dataset_id, doc_id), who.token, body)


def upload_pdf(ingress: httpx.Client, who: Account, dataset_id: str, data: bytes, name: str | None = None) -> dict:
    return upload_text(ingress, who, dataset_id, data, name or f"doc-{uuid.uuid4().hex[:8]}.pdf", mime="application/pdf")


# ----------------------------------------------------------------------------- detail


def test_detail_of_a_text_file_shows_the_defaults_and_no_preview(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(2))
    body = detail(ingress, owner, dataset_id, doc["id"])
    assert (body["chunk_token_num"], body["delimiter"], body["overlapped_percent"]) == (512, DELIMITER, 0)
    assert (body["preview"], body["parseable"], body["suffix"], body["size"], body["pages_total"]) == ("none", True, "txt", doc["size"], None)
    assert body["parser_id"] == "naive" and body["run"] == "0" and body["chunk_count"] == 0
    assert DETAIL_EXTRA <= set(body) and ROW_BANNED.isdisjoint(body)


def test_detail_of_a_thirteen_page_pdf_offers_page_previews(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_pdf(ingress, owner, dataset_id, thirteen_page_pdf())
    body = detail(ingress, owner, dataset_id, doc["id"])
    assert (body["preview"], body["pages_total"], body["suffix"]) == ("pages", 13, "pdf")
    again = detail(ingress, owner, dataset_id, doc["id"])
    assert again == body, "the cached count answers the same"


def test_detail_of_a_damaged_pdf_has_no_preview(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_pdf(ingress, owner, dataset_id, b"%PDF-1.4\n" + garbage_bytes())
    body = detail(ingress, owner, dataset_id, doc["id"])
    assert (body["preview"], body["pages_total"]) == ("none", None)


# ----------------------------------------------------------------------------- list rows


def test_list_rows_carry_the_phase_four_facts_for_a_parsed_and_a_failed_document(ingress: httpx.Client, owner: Account, settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    good = upload_text(ingress, owner, dataset_id, paragraphs(3))
    bad = upload_pdf(ingress, owner, dataset_id, b"%PDF-1.4\n" + garbage_bytes(), "broken.pdf")
    pdf = upload_pdf(ingress, owner, dataset_id, thirteen_page_pdf(), "pages.pdf")
    assert start_parse(ingress, owner, dataset_id, [good["id"], bad["id"], pdf["id"]]).status_code == 200
    done = wait_run(ingress, owner, dataset_id, good["id"], "3", timeout=120)
    failed = wait_run(ingress, owner, dataset_id, bad["id"], "4", timeout=120)
    parsed_pdf = wait_run(ingress, owner, dataset_id, pdf["id"], "3", timeout=180)

    assert done["chunk_count"] == index_count(settings, owner.tenant_id, dataset_id, good["id"]) == 3
    assert done["parseable"] is True and done["enabled"] is True and done["last_log_id"] and done["error"] is None
    assert failed["chunk_count"] == 0 and failed["last_log_id"]
    assert set(failed["error"]) == {"step", "code", "message"} and all(isinstance(v, str) and v for v in failed["error"].values())
    assert str(parsed_pdf["thumbnail"]).startswith("data:image/") and parsed_pdf["pages_total"] == 13
    for row in (done, failed, parsed_pdf):
        assert ROW_BANNED.isdisjoint(row), set(row) & ROW_BANNED


# ----------------------------------------------------------------------------- settings change


def test_patch_changes_the_values_and_leaves_the_parse_state_and_chunks_alone(ingress: httpx.Client, owner: Account, settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(5))
    assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
    before = wait_run(ingress, owner, dataset_id, doc["id"], "3", timeout=120)
    chunks_before = index_count(settings, owner.tenant_id, dataset_id, doc["id"])
    assert before["chunk_count"] == chunks_before == 5

    resp = patch(ingress, owner, dataset_id, doc["id"], {"parser_config": {"chunk_token_num": 256}})
    body = ok(resp)
    assert body["chunk_token_num"] == 256 and body["id"] == doc["id"]
    after = doc_row(ingress, owner, dataset_id, doc["id"])
    assert (after["run"], after["progress"], after["chunk_count"]) == (before["run"], before["progress"], before["chunk_count"])
    assert index_count(settings, owner.tenant_id, dataset_id, doc["id"]) == chunks_before, "no re-chunking"
    assert detail(ingress, owner, dataset_id, doc["id"])["chunk_token_num"] == 256

    other = ok(patch(ingress, owner, dataset_id, doc["id"], {"parser_config": {"delimiter": "##", "overlapped_percent": 10}}))
    assert (other["chunk_token_num"], other["delimiter"], other["overlapped_percent"]) == (256, "##", 10)


def test_patch_refuses_a_method_that_is_not_built_and_a_bad_value(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(2))
    resp = patch(ingress, owner, dataset_id, doc["id"], {"parser_id": "qa"})
    assert resp.status_code == 400 and reason_of(resp) == "chunker_unavailable", resp.text
    resp = patch(ingress, owner, dataset_id, doc["id"], {"parser_config": {"chunk_token_num": 0}})
    assert resp.status_code == 400 and reason_of(resp) == "parser_config_invalid" and resp.json()["data"]["field"] == "chunk_token_num", resp.text
    assert detail(ingress, owner, dataset_id, doc["id"])["chunk_token_num"] == 512
    assert patch(ingress, owner, dataset_id, doc["id"], {"parser_id": "naive"}).status_code == 200


def test_patch_refuses_an_extra_field(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(2))
    for body in ({"run": "1"}, {"created_by": owner.user_id}, {"parser_config": {"unknown_pages": [[1, 2]]}}, {"parser_config": {"chunk_token_num": 64, "x": 1}}):
        resp = patch(ingress, owner, dataset_id, doc["id"], body)
        assert resp.status_code == 400, (body, resp.text)
    assert detail(ingress, owner, dataset_id, doc["id"])["chunk_token_num"] == 512


def test_patch_persists_supported_page_and_layout_settings(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(2))
    saved = ok(patch(ingress, owner, dataset_id, doc["id"], {"parser_config": {"pages": [[1, 2]], "layout_recognize": False}}))
    assert saved["pages"] == [[1, 2]] and saved["layout_recognize"] is False
    assert saved["run"] == "0"


def test_patch_during_a_running_parse_is_409_parse_running(ingress: httpx.Client, owner: Account, fake: FakeProvider) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(LONG))
    fake.delay_ms = 2000
    try:
        assert start_parse(ingress, owner, dataset_id, [doc["id"]]).status_code == 200
        resp = patch(ingress, owner, dataset_id, doc["id"], {"parser_config": {"chunk_token_num": 64}})
        assert resp.status_code == 409 and reason_of(resp) == "parse_running", resp.text
        assert start_parse(ingress, owner, dataset_id, [doc["id"]], run="2").status_code == 200
    finally:
        fake.delay_ms = 0
    assert detail(ingress, owner, dataset_id, doc["id"])["chunk_token_num"] == 512


def test_dataset_update_refuses_a_method_that_is_not_built(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    resp = call(ingress, "PUT", f"{DATASETS}/{dataset_id}", owner.token, {"parser_id": "qa"})
    assert resp.status_code == 400 and reason_of(resp) == "chunker_unavailable", resp.text
    assert ok(call(ingress, "GET", f"{DATASETS}/{dataset_id}", owner.token))["parser_id"] == "naive"
    resp = call(ingress, "PUT", f"{DATASETS}/{dataset_id}", owner.token, {"parser_id": "bogus"})
    assert resp.status_code == 400 and reason_of(resp) == "dataset_invalid", "an unknown id keeps the Phase 3 answer"


# ----------------------------------------------------------------------------- who and where


def test_only_the_uploader_the_creator_and_the_owner_may_change_settings(ingress: httpx.Client, registry: AccountRegistry, owner: Account) -> None:  # noqa: F811
    alice, bob = registry.register(prefix="detali"), registry.register(prefix="detbob")
    join(ingress, owner, alice)
    join(ingress, owner, bob)
    team = new_dataset(ingress, owner, permission="team")
    mine = upload_text(ingress, alice, team, paragraphs(2))
    resp = patch(ingress, bob, team, mine["id"], {"parser_config": {"chunk_token_num": 77}})
    assert resp.status_code == 403 and resp.json() == FORBIDDEN, resp.text
    assert detail(ingress, bob, team, mine["id"])["chunk_token_num"] == 512, "a member may read what they may not change"
    assert ok(patch(ingress, alice, team, mine["id"], {"parser_config": {"chunk_token_num": 78}}))["chunk_token_num"] == 78
    assert ok(patch(ingress, owner, team, mine["id"], {"parser_config": {"chunk_token_num": 79}}))["chunk_token_num"] == 79


def test_an_api_token_of_the_owner_reads_and_changes_its_own_document(ingress: httpx.Client, owner: Account) -> None:
    """The other half of "judged as its subject" (a token that is neither uploader nor creator is refused) is pinned in test_document_settings."""
    created = ingress.post(TOKENS, headers=_bearer(owner.token))
    assert created.status_code == 200, created.text
    token = created.json()["data"]["token"]
    own = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, own, paragraphs(2))
    assert detail_by_token(ingress, token, own, doc["id"]).status_code == 200
    resp = call(ingress, "PATCH", path_of(own, doc["id"]), token, {"parser_config": {"chunk_token_num": 91}})
    assert resp.status_code == 200 and ok(resp)["chunk_token_num"] == 91, resp.text


def detail_by_token(ingress: httpx.Client, token: str, dataset_id: str, doc_id: str) -> httpx.Response:
    return call(ingress, "GET", path_of(dataset_id, doc_id), token)


def test_unknown_foreign_and_private_ids_are_the_one_not_found(ingress: httpx.Client, registry: AccountRegistry, owner: Account) -> None:  # noqa: F811
    stranger, member = registry.register(prefix="detstr"), registry.register(prefix="detmem")
    join(ingress, owner, member)
    private = new_dataset(ingress, owner)
    team = new_dataset(ingress, owner, permission="team")
    doc = upload_text(ingress, owner, private, paragraphs(2))
    absent = uuid.uuid4().hex
    body = {"parser_config": {"chunk_token_num": 64}}
    for who in (stranger, member):
        for method, payload in (("GET", None), ("PATCH", body)):
            resp = call(ingress, method, path_of(private, doc["id"]), who.token, payload)
            assert resp.status_code == 404 and resp.json() == NOT_FOUND, (method, resp.text)
    for method, payload in (("GET", None), ("PATCH", body)):
        for dataset_id, doc_id in ((private, absent), (absent, doc["id"]), ("not-an-id", doc["id"]), (private, "not-an-id"), (team, doc["id"])):
            resp = call(ingress, method, path_of(dataset_id, doc_id), owner.token, payload)
            assert resp.status_code == 404 and resp.json() == NOT_FOUND, (method, dataset_id, doc_id, resp.text)
    assert detail(ingress, owner, private, doc["id"])["chunk_token_num"] == 512
