"""Chunk list, add, edit and switch against the real MySQL and Elasticsearch with the loopback embedding provider (plan 04-18).

CHUNK-16, CHUNK-18..21, IDX-07, KB-19, BE-06, D-10, D-11, D-12, D-26, R-155. The loopback provider is the other end of the wire (its ``embed_mode``
flips it to refuse, never answer or rate-limit); the index and the database are the real ones. Waiting never uses a sleep.
"""

from __future__ import annotations

import dataclasses
import io
import re
import secrets
from collections.abc import Iterator
from typing import Any

import pytest
import valkey

from api.db.services import chunk_service as cs
from api.db.services import document_service as docs
from api.db.services import ingestion_service as ing
from api.db.services.auth_service import AUTH_API, Principal
from api.db.services.document_service import UploadItem
from api.db.services.service_errors import Kind, ServiceError
from common.settings import load_settings
from rag.chunking.types import Chunk
from rag.nlp.token_count import count_tokens
from rag.parsers.types import PageBox
from rag.svr.chunk_doc import build_row
from test.helpers.accounts import AccountRegistry
from test.helpers.doc_store_contract import unit_vector
from test.helpers.fake_provider import FakeProvider, running_fake_provider
from test.helpers.ingest import DIMENSION, World, add_document, cleanup_tasks, make_pipeline_world
from test.helpers.uploads import sql
from test.integration.test_document_service import team_dataset_of
from test.integration.test_knowledgebase_service import join, principal_of
from test.integration.test_upload_service import _bound_database  # noqa: F401  (autouse module fixture)
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.integration

EMBEDDINGS = "/v1/embeddings"
MANUAL_ID = re.compile(r"[0-9a-f]{32}_m_[0-9a-f]{32}")


@pytest.fixture
def registry() -> Iterator[AccountRegistry]:
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        cleanup_tasks(accounts)
        accounts.cleanup()


@pytest.fixture
def fake() -> Iterator[FakeProvider]:
    with running_fake_provider() as provider:
        yield provider


@pytest.fixture
def world(registry, fake) -> World:
    return make_pipeline_world(registry, fake)


# ----------------------------------------------------------------------------- helpers


def seed(world: World, doc_id: str, count: int, *, text: str = "alpha{i} revenue grows", dataset=None) -> list[str]:
    """Parsed-looking chunks written straight into the real index (rows built by the pipeline's own ``build_row``), then the totals settled."""
    dataset = dataset or world.dataset
    store = world.store()
    store.create_idx(world.index, dataset.id, DIMENSION, "naive")
    rows = []
    for i in range(count):
        page = 1 + i // 10
        body = text.format(i=i)
        chunk = Chunk(body, (PageBox(page, 10.0, 20.0, 30.0, 40.0),), {page: (612.0, 792.0)}, count_tokens(body), i)
        rows.append(
            build_row(
                chunk, index=i, doc_id=doc_id, kb_id=dataset.id, doc_name="seed.txt", task_id="seeded", from_page=0, to_page=1000000,
                vector=unit_vector(i % DIMENSION), enabled=True,
            )
        )
    assert store.insert(rows, world.index, dataset.id) == []
    cs_settle(world, dataset, doc_id)
    return [r["id"] for r in rows]


def cs_settle(world: World, dataset, doc_id: str) -> None:
    from api.db.services.totals_service import settle_totals

    settle_totals(world.settings, world.owner.tenant_id, dataset.id, doc_id, doc_store=world.store())


def document(world: World, name: str = "seed.txt") -> str:
    return add_document(world, name, f"{name} body".encode())


def stored(world: World, chunk_id: str, dataset=None) -> dict[str, Any]:
    found = world.store().get(chunk_id, world.index, [(dataset or world.dataset).id])
    assert found is not None
    return found


def listing(world: World, doc_id: str, who=None, dataset=None, **kw: Any) -> dict[str, Any]:
    who, dataset = who or world.owner, dataset or world.dataset
    visible = cs.authorize_read(principal_of(who), dataset.id)
    return cs.list_chunks(world.embed_settings, visible, doc_id, doc_store=world.store(), **kw)


def add(world: World, doc_id: str, text: object, who=None, dataset=None, principal: Principal | None = None) -> dict[str, Any]:
    who, dataset = who or world.owner, dataset or world.dataset
    who_p = principal or principal_of(who)
    visible = cs.authorize_write(who_p, dataset.id)
    return cs.create_chunk(world.embed_settings, visible, who_p, doc_id, text, doc_store=world.store())


def edit(world: World, doc_id: str, chunk_id: str, who=None, dataset=None, principal: Principal | None = None, **kw: Any) -> dict[str, Any]:
    who, dataset = who or world.owner, dataset or world.dataset
    who_p = principal or principal_of(who)
    visible = cs.authorize_write(who_p, dataset.id)
    return cs.update_chunk(world.embed_settings, visible, who_p, doc_id, chunk_id, doc_store=world.store(), **kw)


def refused(call) -> ServiceError:
    with pytest.raises(ServiceError) as err:
        call()
    return err.value


def embed_calls(fake: FakeProvider) -> int:
    return len(fake.hits(EMBEDDINGS))


def doc_numbers(doc_id: str) -> tuple[int, int]:
    chunks, tokens = sql("SELECT `chunk_num`, `token_num` FROM `document` WHERE `id` = %s", (doc_id,))[0]
    return int(chunks), int(tokens)


def dataset_numbers(dataset_id: str) -> tuple[int, int]:
    chunks, tokens = sql("SELECT `chunk_num`, `token_num` FROM `knowledgebase` WHERE `id` = %s", (dataset_id,))[0]
    return int(chunks), int(tokens)


class Wrapped:
    """The real store with some calls replaced; everything else is delegated."""

    def __init__(self, real, **over: Any) -> None:
        self._real = real
        self._over = over

    def __getattr__(self, name: str) -> Any:
        return self._over.get(name) or getattr(self._real, name)


# ----------------------------------------------------------------------------- list


def test_list_pages_in_document_order_with_positions_and_page_sizes(world):
    doc_id = document(world)
    seed(world, doc_id, 25)
    first = listing(world, doc_id)
    assert first["total"] == 25 and len(first["items"]) == 20
    assert [i["text"] for i in first["items"]] == [f"alpha{i} revenue grows" for i in range(20)]
    one = first["items"][0]
    assert set(one) == {"id", "text", "positions", "origin", "enabled"}
    assert one["positions"] == [{"page": 1, "x0": 10, "top": 20, "x1": 30, "bottom": 40}] and one["origin"] == "parsed" and one["enabled"] is True
    assert first["page_sizes"] == {"1": [612.0, 792.0], "2": [612.0, 792.0]}, "one entry per page the page references"
    second = listing(world, doc_id, page=2)
    assert [i["text"] for i in second["items"]] == [f"alpha{i} revenue grows" for i in range(20, 25)]
    assert second["page_sizes"] == {"3": [612.0, 792.0]}


def test_size_and_page_limits_are_refused(world):
    doc_id = document(world)
    seed(world, doc_id, 3)
    assert refused(lambda: listing(world, doc_id, size=101)).reason == "query_invalid"
    assert refused(lambda: listing(world, doc_id, size=0)).reason == "query_invalid"
    assert refused(lambda: listing(world, doc_id, page=0)).reason == "query_invalid"
    assert refused(lambda: listing(world, doc_id, page=10_000, size=100)).reason == "query_invalid"
    assert refused(lambda: listing(world, doc_id, available=2)).reason == "query_invalid"


def test_keywords_filter_in_document_order_and_odd_text_is_never_an_error(world):
    doc_id = document(world)
    seed(world, doc_id, 12, text="chunk{i} revenue")
    mid = add(world, doc_id, "zebra stripes only here")
    assert isinstance(listing(world, doc_id, keywords="what is (revenue")["items"], list)
    found = listing(world, doc_id, keywords="revenue")
    assert found["total"] == 12 and [i["text"] for i in found["items"]] == [f"chunk{i} revenue" for i in range(12)]
    only = listing(world, doc_id, keywords="ZEBRA")
    assert [i["id"] for i in only["items"]] == [mid["id"]]
    for odd in ("((", '"unclosed', "a AND OR NOT", "*", "-", "x:y", "\\", "~~~"):
        assert isinstance(listing(world, doc_id, keywords=odd)["items"], list), odd
    assert refused(lambda: listing(world, doc_id, keywords="x" * 129)).reason == "query_invalid"


def test_available_filters_on_the_chunks_own_switch(world):
    doc_id = document(world)
    ids = seed(world, doc_id, 6)
    for chunk_id in ids[:2]:
        edit(world, doc_id, chunk_id, available=False)
    off = listing(world, doc_id, available=0)
    on = listing(world, doc_id, available=1)
    assert [i["id"] for i in off["items"]] == ids[:2] and all(i["enabled"] is False for i in off["items"])
    assert [i["id"] for i in on["items"]] == ids[2:] and off["total"] == 2 and on["total"] == 4


# ----------------------------------------------------------------------------- create


def test_create_embeds_once_and_stores_a_manual_chunk_last_with_totals_settled(world, fake):
    doc_id = document(world)
    seed(world, doc_id, 3)
    before_doc, before_dataset = doc_numbers(doc_id), dataset_numbers(world.dataset.id)
    calls = embed_calls(fake)
    made = add(world, doc_id, "  a note I wrote by hand  ")
    assert embed_calls(fake) == calls + 1
    assert MANUAL_ID.fullmatch(made["id"]) and made["id"].startswith(doc_id) and made["origin"] == "manual" and made["positions"] == []
    assert made["text"] == "a note I wrote by hand" and made["enabled"] is True
    row = stored(world, made["id"])
    vector = row[f"q_{DIMENSION}_vec"]
    assert len(vector) == DIMENSION and abs(sum(x * x for x in vector) - 1.0) < 1e-5
    assert row["order_int"] == 2_000_000_000 and row["origin_kwd"] == "manual" and row["doc_enabled_int"] == 1 and row["kb_id"] == world.dataset.id
    assert row["token_num_int"] == count_tokens("a note I wrote by hand")
    items = listing(world, doc_id)["items"]
    assert items[-1]["id"] == made["id"] and len(items) == 4
    tokens = count_tokens("a note I wrote by hand")
    assert doc_numbers(doc_id) == (before_doc[0] + 1, before_doc[1] + tokens)
    assert dataset_numbers(world.dataset.id) == (before_dataset[0] + 1, before_dataset[1] + tokens)


def test_a_chunk_added_to_a_switched_off_document_is_off_with_it(world):
    doc_id = document(world)
    seed(world, doc_id, 2)
    visible = docs.authorize_removal(principal_of(world.owner), world.dataset.id)
    docs.set_documents_enabled(world.settings, visible, principal_of(world.owner), [doc_id], False)
    made = add(world, doc_id, "added while the document is off")
    assert stored(world, made["id"])["doc_enabled_int"] == 0 and stored(world, made["id"])["available_int"] == 1


def test_create_on_a_document_that_was_never_parsed_makes_the_index_ready(world):
    doc_id = document(world)
    made = add(world, doc_id, "first chunk of a fresh document")
    assert listing(world, doc_id)["items"][0]["id"] == made["id"] and doc_numbers(doc_id)[0] == 1


def test_text_that_is_empty_or_too_long_is_refused_before_any_provider_call(world, fake):
    doc_id = document(world)
    calls = embed_calls(fake)
    assert refused(lambda: add(world, doc_id, "   ")).kind is Kind.INVALID
    assert refused(lambda: add(world, doc_id, None)).kind is Kind.INVALID
    assert refused(lambda: add(world, doc_id, "x" * 32001)).reason == "chunk_too_long"
    assert embed_calls(fake) == calls


def test_text_over_the_models_token_limit_is_chunk_too_long(world, fake):
    doc_id = document(world)
    calls = embed_calls(fake)
    text = "日本語の文章です。" * 3400  # under 32000 characters, far over the model's token limit
    assert len(text) <= cs.MAX_CHUNK_CHARS
    assert refused(lambda: add(world, doc_id, text)).reason == "chunk_too_long"
    assert embed_calls(fake) == calls
    chunk_id = seed(world, doc_id, 1)[0]
    assert refused(lambda: edit(world, doc_id, chunk_id, text=text)).reason == "chunk_too_long"


# ----------------------------------------------------------------------------- edit and D-11


def test_an_edit_replaces_text_tokens_and_vector_together_and_marks_the_chunk_edited(world, fake):
    doc_id = document(world)
    ids = seed(world, doc_id, 4)
    before = stored(world, ids[1])
    totals = (doc_numbers(doc_id), dataset_numbers(world.dataset.id))
    fake.embedding_dim = DIMENSION
    changed = edit(world, doc_id, ids[1], text="the new text about margins")
    after = stored(world, ids[1])
    assert changed["text"] == "the new text about margins" and changed["origin"] == "edited"
    assert changed["positions"] == [{"page": 1, "x0": 10, "top": 20, "x1": 30, "bottom": 40}]
    assert after["content_with_weight"] == "the new text about margins" and after["content_ltks"] == "the new text about margins"
    assert after["token_num_int"] == count_tokens("the new text about margins")
    assert after[f"q_{DIMENSION}_vec"] != before[f"q_{DIMENSION}_vec"]
    assert after["origin_kwd"] == "edited" and after["position_int"] == before["position_int"] and after["order_int"] == before["order_int"]
    assert after["available_int"] == before["available_int"] and after["doc_enabled_int"] == before["doc_enabled_int"]
    delta = count_tokens("the new text about margins") - count_tokens(before["content_with_weight"])
    assert doc_numbers(doc_id) == (totals[0][0], totals[0][1] + delta)
    assert dataset_numbers(world.dataset.id) == (totals[1][0], totals[1][1] + delta)
    assert [i["origin"] for i in listing(world, doc_id)["items"]] == ["parsed", "edited", "parsed", "parsed"]


def test_a_manual_chunk_stays_manual_when_edited(world):
    doc_id = document(world)
    made = add(world, doc_id, "first draft")
    again = edit(world, doc_id, made["id"], text="second draft")
    assert again["origin"] == "manual" and again["text"] == "second draft"


@pytest.mark.parametrize(
    ("mode", "reason"),
    [("refuse", "provider_refused"), ("timeout", "provider_timeout"), ("ratelimit", "provider_rate_limited")],
)
def test_a_failed_embedding_leaves_text_and_vector_untouched_byte_for_byte(world, fake, mode, reason):
    doc_id = document(world)
    ids = seed(world, doc_id, 3)
    before = stored(world, ids[0])
    totals = (doc_numbers(doc_id), dataset_numbers(world.dataset.id))
    fake.embed_mode = mode
    err = refused(lambda: edit(world, doc_id, ids[0], text="text that will never be stored"))
    assert err.reason == reason
    assert stored(world, ids[0]) == before, "text, tokens, vector, origin and flags are all as they were"
    failed_add = refused(lambda: add(world, doc_id, "a chunk that will never exist"))
    assert failed_add.reason == reason
    assert listing(world, doc_id)["total"] == 3
    assert (doc_numbers(doc_id), dataset_numbers(world.dataset.id)) == totals
    fake.embed_mode = "ok"
    assert edit(world, doc_id, ids[0], text="now it works")["text"] == "now it works", "no pending state was left behind"


def test_an_embedding_that_finishes_after_the_deadline_is_dropped_not_written(world, monkeypatch):
    doc_id = document(world)
    ids = seed(world, doc_id, 1)
    before = stored(world, ids[0])
    monkeypatch.setattr(cs, "WRITE_DEADLINE_SECONDS", -1.0)
    assert refused(lambda: edit(world, doc_id, ids[0], text="late")).reason == "provider_timeout"
    assert refused(lambda: add(world, doc_id, "late")).reason == "provider_timeout"
    assert stored(world, ids[0]) == before and listing(world, doc_id)["total"] == 1


def test_the_refusal_text_never_carries_a_key(world, fake):
    doc_id = document(world)
    ids = seed(world, doc_id, 1)
    fake.embed_mode = "refuse"
    err = refused(lambda: edit(world, doc_id, ids[0], text="x"))
    assert world.api_key not in err.message and len(err.message) <= 300


def test_the_switch_alone_calls_no_provider_and_both_together_embed_once(world, fake):
    doc_id = document(world)
    ids = seed(world, doc_id, 2)
    calls = embed_calls(fake)
    off = edit(world, doc_id, ids[0], available=False)
    assert off["enabled"] is False and off["origin"] == "parsed" and embed_calls(fake) == calls
    both = edit(world, doc_id, ids[1], text="rewritten", available=False)
    assert both["enabled"] is False and both["origin"] == "edited" and embed_calls(fake) == calls + 1
    assert refused(lambda: edit(world, doc_id, ids[1])).kind is Kind.INVALID
    assert refused(lambda: edit(world, doc_id, ids[1], available="no")).kind is Kind.INVALID


def test_a_chunk_switched_off_stays_off_after_its_document_is_switched_off_and_on(world):
    doc_id = document(world)
    ids = seed(world, doc_id, 3)
    edit(world, doc_id, ids[1], available=False)
    visible = docs.authorize_removal(principal_of(world.owner), world.dataset.id)
    docs.set_documents_enabled(world.settings, visible, principal_of(world.owner), [doc_id], False)
    docs.set_documents_enabled(world.settings, visible, principal_of(world.owner), [doc_id], True)
    flags = {i: (stored(world, i)["available_int"], stored(world, i)["doc_enabled_int"]) for i in ids}
    assert flags == {ids[0]: (1, 1), ids[1]: (0, 1), ids[2]: (1, 1)}
    assert [i["enabled"] for i in listing(world, doc_id)["items"]] == [True, False, True]


def test_an_index_that_reports_a_failed_update_is_unavailable_and_changes_nothing(world):
    doc_id = document(world)
    ids = seed(world, doc_id, 1)
    before = stored(world, ids[0])
    partial = Wrapped(world.store(), update=lambda *a, **k: False)
    visible = cs.authorize_write(principal_of(world.owner), world.dataset.id)
    err = refused(lambda: cs.update_chunk(world.embed_settings, visible, principal_of(world.owner), doc_id, ids[0], text="never stored", doc_store=partial))
    assert err.kind is Kind.UNAVAILABLE and err.reason == "index_unavailable"
    assert stored(world, ids[0]) == before
    err = refused(lambda: cs.update_chunk(world.embed_settings, visible, principal_of(world.owner), doc_id, ids[0], available=False, doc_store=partial))
    assert err.reason == "index_unavailable" and stored(world, ids[0]) == before


def test_an_index_that_fails_an_insert_is_unavailable_and_adds_nothing(world):
    doc_id = document(world)
    seed(world, doc_id, 2)
    totals = doc_numbers(doc_id)
    broken = Wrapped(world.store(), insert=lambda rows, *a, **k: [r["id"] for r in rows])
    visible = cs.authorize_write(principal_of(world.owner), world.dataset.id)
    err = refused(lambda: cs.create_chunk(world.embed_settings, visible, principal_of(world.owner), doc_id, "never stored", doc_store=broken))
    assert err.kind is Kind.UNAVAILABLE and err.reason == "index_unavailable"
    assert listing(world, doc_id)["total"] == 2 and doc_numbers(doc_id) == totals


# ----------------------------------------------------------------------------- state, roles, scope


def test_writes_are_refused_with_409_while_the_document_is_parsing_but_reads_work(world, fake):
    doc_id = document(world)
    ids = seed(world, doc_id, 2)
    sql("UPDATE `document` SET `run` = '1' WHERE `id` = %s", (doc_id,))
    calls = embed_calls(fake)
    for call in (lambda: add(world, doc_id, "x"), lambda: edit(world, doc_id, ids[0], text="x"), lambda: edit(world, doc_id, ids[0], available=False)):
        err = refused(call)
        assert err.kind is Kind.CONFLICT and err.reason == "parse_running"
    assert embed_calls(fake) == calls
    assert listing(world, doc_id)["total"] == 2


def test_only_the_uploader_creator_owner_or_admin_may_write_and_a_token_is_judged_as_its_subject(world, registry):
    creator, uploader, plain = (registry.register(prefix=p) for p in ("chcre", "chupl", "chpla"))
    for member in (creator, uploader, plain):
        join(world.owner, member)
    dataset = team_dataset_of(world.settings, world.owner, creator)
    visible = docs.authorize_upload(principal_of(uploader), dataset.id)
    made = docs.upload_documents(world.settings, visible, uploader.user_id, [UploadItem("m.txt", "text/plain", io.BytesIO(b"member document"))])
    doc_id = made[0]["id"]
    ids = seed(world, doc_id, 2, dataset=dataset)

    assert len(listing(world, doc_id, who=plain, dataset=dataset)["items"]) == 2, "a reader needs only visibility"
    assert refused(lambda: add(world, doc_id, "x", who=plain, dataset=dataset)).kind is Kind.FORBIDDEN
    assert refused(lambda: edit(world, doc_id, ids[0], who=plain, dataset=dataset, available=False)).kind is Kind.FORBIDDEN
    assert stored(world, ids[0], dataset)["available_int"] == 1
    assert add(world, doc_id, "by the uploader", who=uploader, dataset=dataset)["origin"] == "manual"
    assert edit(world, doc_id, ids[0], who=creator, dataset=dataset, available=False)["enabled"] is False
    assert edit(world, doc_id, ids[0], who=world.owner, dataset=dataset, available=True)["enabled"] is True
    token = Principal(world.owner.user_id, world.owner.tenant_id, "owner", AUTH_API, False)
    assert refused(lambda: add(world, doc_id, "x", dataset=dataset, principal=token)).kind is Kind.FORBIDDEN


def test_a_chunk_of_another_document_or_dataset_or_a_malformed_id_is_the_one_not_found(world):
    doc_id, other_doc = document(world, "one.txt"), document(world, "two.txt")
    ids = seed(world, doc_id, 1)
    other_ids = seed(world, other_doc, 1)
    second = team_dataset_of(world.settings, world.owner, world.owner)
    foreign_doc = add_document_to(world, second)
    foreign_ids = seed(world, foreign_doc, 1, dataset=second)
    snapshot = stored(world, ids[0])

    assert refused(lambda: edit(world, doc_id, other_ids[0], available=False)).kind is Kind.NOT_FOUND
    assert refused(lambda: edit(world, doc_id, foreign_ids[0], available=False)).kind is Kind.NOT_FOUND
    for bad in ("nope", "../x", f"{doc_id}_m_xyz", f"{doc_id}_1; DROP", "", f"{doc_id}_"):
        assert refused(lambda b=bad: edit(world, doc_id, b, available=False)).kind is Kind.NOT_FOUND, bad
    assert refused(lambda: edit(world, doc_id, f"{doc_id}_999999", available=False)).kind is Kind.NOT_FOUND
    assert refused(lambda: edit(world, foreign_doc, foreign_ids[0], available=False)).kind is Kind.NOT_FOUND, "the document is not in this dataset"
    assert refused(lambda: add(world, foreign_doc, "x")).kind is Kind.NOT_FOUND
    assert refused(lambda: listing(world, foreign_doc)).kind is Kind.NOT_FOUND
    assert refused(lambda: listing(world, "nope")).kind is Kind.NOT_FOUND
    assert stored(world, ids[0]) == snapshot and stored(world, other_ids[0])["available_int"] == 1


def add_document_to(world: World, dataset) -> str:
    visible = docs.authorize_upload(principal_of(world.owner), dataset.id)
    made = docs.upload_documents(world.settings, visible, world.owner.user_id, [UploadItem("f.txt", "text/plain", io.BytesIO(b"foreign document"))])
    return made[0]["id"]


# ----------------------------------------------------------------------------- the write limit


def test_adds_and_edits_share_a_per_tenant_window_with_parse_numbers():
    cfg = load_settings()
    cfg = dataclasses.replace(cfg, ingest=dataclasses.replace(cfg.ingest, parse_rate_max=2, parse_rate_window_seconds=60))
    tenant = f"t{secrets.token_hex(8)}"
    try:
        ing.write_rate_guard(cfg, tenant)
        ing.write_rate_guard(cfg, tenant)
        err = refused(lambda: ing.write_rate_guard(cfg, tenant))
        assert err.kind is Kind.RATE_LIMITED and err.retry_after is not None and err.retry_after > 0
        ing.write_rate_guard(cfg, f"t{secrets.token_hex(8)}")
    finally:
        rd = cfg.redis
        raw = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db)
        try:
            raw.delete(f"chunk:{tenant}")
        finally:
            raw.close()


def test_chinese_edit_replaces_offsets_and_english_edit_clears_them(world, fake):
    doc_id = document(world)
    ids = seed(world, doc_id, 1, text="檔案保存期限")
    fake.embedding_dim = DIMENSION
    edit(world, doc_id, ids[0], text="ＡＢＣ 新檔案")
    row = stored(world, ids[0])
    terms = row["content_ltks"].split()
    spans = row["content_token_offsets_int"]
    assert len(terms) == len(spans)
    assert row["content_with_weight"][slice(*spans[terms.index("abc")])] == "ＡＢＣ"
    edit(world, doc_id, ids[0], text="English only")
    row = stored(world, ids[0])
    assert row["content_ltks"] == "english only"
    assert row["content_token_offsets_int"] == []
