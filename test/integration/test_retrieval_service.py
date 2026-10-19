"""The retrieval-test service on the real MySQL, Elasticsearch and Valkey (plan 05-04; RETR-16..18, RETR-23, KB-18, TEN-03, D-19).

Chunk rows are written through the port with the pipeline's own ``build_row`` and planted vectors; the query vector comes from the ``embedder``
seam so the golden order is fixed by the weights alone. The embedding provider is the loopback fake where a test goes through the bundle.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import valkey

from api.db.services import knowledgebase_service as kb
from api.db.services import tenant_model_service as structure
from api.db.services import retrieval_service as rs
from api.db.services.auth_service import AUTH_JWT, Principal
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_model_service import NewModel
from api.db.services.tenant_scope import ActingScope
from common.doc_store.doc_store_base import DocStoreError, SearchResult
from rag.chunking.types import Chunk
from rag.nlp.token_count import count_tokens
from rag.svr.chunk_doc import build_row
from test.helpers.accounts import AccountRegistry
from test.helpers.doc_store_contract import QUERY_VECTOR, RARE_KEYWORD, unit_vector
from test.helpers.fake_provider import FakeProvider, running_fake_provider
from test.helpers.ingest import DIMENSION, World, add_document, cleanup_tasks, make_pipeline_world
from test.helpers.uploads import sql
from test.integration.test_knowledgebase_service import join, principal_of
from test.integration.test_upload_service import _bound_database  # noqa: F401  (autouse module fixture)
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.integration

K_TEXT = f"field notes about {RARE_KEYWORD} samples"
S_TEXT = "plain unrelated sentence"
EMBEDDINGS = "/v1/embeddings"


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


def scope_of(world: World, role: str = "owner") -> ActingScope:
    return ActingScope(tenant_id=world.owner.tenant_id, role=role, subject=role)


def planted_query(_text: str) -> list[float]:
    return list(QUERY_VECTOR)


def plant(world: World, dataset, doc_id: str, name: str, text: str, axis: int, **extra: Any) -> str:
    """One chunk of ``doc_id`` with a planted vector, written into the real index."""
    store = world.store()
    store.create_idx(world.index, dataset.id, DIMENSION, "naive")
    chunk = Chunk(text, (), {}, count_tokens(text), 0)
    row = build_row(chunk, index=0, doc_id=doc_id, kb_id=dataset.id, doc_name="planted.txt", task_id="t", from_page=0, to_page=1, vector=unit_vector(axis), enabled=True)
    row["id"] = name
    row.update(extra)
    assert store.insert([row], world.index, dataset.id) == []
    return name


def plant_golden(world: World, dataset=None) -> str:
    dataset = dataset or world.dataset
    doc_id = add_document(world, f"golden-{uuid.uuid4().hex[:6]}.txt", b"golden body")
    plant(world, dataset, doc_id, f"k-{doc_id[:6]}", K_TEXT, 1)
    plant(world, dataset, doc_id, f"s-{doc_id[:6]}", S_TEXT, 0)
    return doc_id


def ask(world: World, body: dict[str, Any], *, who=None, scope: ActingScope | None = None, settings=None, doc_store=None, embedder=planted_query, reranker=None) -> dict[str, Any]:
    who = who or world.owner
    return rs.search(principal_of(who), scope or scope_of(world), body, settings or world.embed_settings, doc_store=doc_store or world.store(), embedder=embedder, reranker=reranker)


def body_of(world: World, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {"dataset_ids": [world.dataset.id], "question": RARE_KEYWORD, "similarity_threshold": 0.0}
    values.update(overrides)
    return values


def refused(call) -> ServiceError:
    with pytest.raises(ServiceError) as err:
        call()
    return err.value


def kinds_of_ids(view: dict[str, Any]) -> list[str]:
    return [c["chunk_id"].split("-")[0] for c in view["chunks"]]


# ----------------------------------------------------------------------------- shape and scores


def test_a_hit_carries_ids_names_positions_and_the_three_scores(world):
    plant_golden(world)
    view = ask(world, body_of(world, vector_similarity_weight=0.3))
    assert view["total"] == 2 and view["rerank_applied"] is False
    assert set(view["timings"]) == {"embed_ms", "search_ms", "rerank_ms"}
    chunk = view["chunks"][0]
    assert {"chunk_id", "content", "doc_id", "doc_name", "dataset_id", "positions", "page_sizes", "similarity", "term_similarity", "vector_similarity"} <= set(chunk)
    assert chunk["dataset_id"] == world.dataset.id and chunk["doc_name"] == "planted.txt" and "rerank_similarity" not in chunk
    assert view["doc_aggs"] == [{"doc_id": chunk["doc_id"], "doc_name": "planted.txt", "count": 2}]
    json.dumps(view, allow_nan=False)


def test_weight_zero_orders_by_the_keyword_share_and_weight_one_by_the_vector_share(world):
    plant_golden(world)
    text_led = ask(world, body_of(world, vector_similarity_weight=0))
    assert kinds_of_ids(text_led) == ["k", "s"] and all(c["similarity"] == c["term_similarity"] for c in text_led["chunks"])
    vector_led = ask(world, body_of(world, vector_similarity_weight=1))
    assert kinds_of_ids(vector_led) == ["s", "k"] and all(c["similarity"] == c["vector_similarity"] for c in vector_led["chunks"])


def test_a_higher_threshold_returns_fewer_hits(world):
    plant_golden(world)
    assert ask(world, body_of(world, vector_similarity_weight=0))["total"] == 2
    strict = ask(world, body_of(world, vector_similarity_weight=0, similarity_threshold=0.9))
    assert kinds_of_ids(strict) == ["k"] and strict["total"] == 1


def test_two_datasets_of_one_workspace_are_searched_together(world):
    second = kb.create_dataset(world.settings, scope_of(world), world.owner.user_id, kb.CreateRequest(name=f"second-{uuid.uuid4().hex[:6]}"))
    plant_golden(world)
    plant_golden(world, second)
    view = ask(world, body_of(world, dataset_ids=[world.dataset.id, second.id]))
    assert {c["dataset_id"] for c in view["chunks"]} == {world.dataset.id, second.id}


def test_doc_ids_narrow_the_search_and_an_empty_list_finds_nothing(world):
    first, second = plant_golden(world), plant_golden(world)
    view = ask(world, body_of(world, doc_ids=[first]))
    assert {c["doc_id"] for c in view["chunks"]} == {first} and second not in {c["doc_id"] for c in view["chunks"]}
    assert ask(world, body_of(world, doc_ids=[]))["total"] == 0


def test_paging_is_stable(world):
    plant_golden(world)
    plant_golden(world)
    one = ask(world, body_of(world, size=2, page=1))
    two = ask(world, body_of(world, size=2, page=2))
    assert one["total"] == two["total"] == 4 and len(one["chunks"]) == 2 and len(two["chunks"]) == 2
    assert not {c["chunk_id"] for c in one["chunks"]} & {c["chunk_id"] for c in two["chunks"]}


def test_a_deleted_document_is_pruned_even_when_its_chunks_remain(world):
    doc_id = plant_golden(world)
    assert ask(world, body_of(world))["total"] == 2
    sql("DELETE FROM `document` WHERE `id` = %s", (doc_id,))
    assert ask(world, body_of(world))["total"] == 0


# ----------------------------------------------------------------------------- authorisation


def test_a_foreign_and_an_absent_dataset_id_are_the_one_not_found(world, registry, fake):
    plant_golden(world)
    foreign = make_pipeline_world(registry, fake).dataset  # another workspace's dataset
    seen = []
    for dataset_id in (foreign.id, uuid.uuid4().hex):
        err = refused(lambda dataset_id=dataset_id: ask(world, body_of(world, dataset_ids=[world.dataset.id, dataset_id])))
        seen.append((err.kind, err.reason, err.message))
    assert len({tuple(s) for s in seen}) == 1 and seen[0][0] is Kind.NOT_FOUND


def test_a_foreign_dataset_never_reaches_the_index(world, registry):
    """No search runs when any id is refused (the doc store is a recorder)."""
    calls: list[str] = []

    class Recorder:
        def search(self, *a, **kw):
            calls.append("search")
            raise AssertionError("no search may run")

    err = refused(lambda: ask(world, body_of(world, dataset_ids=[uuid.uuid4().hex]), doc_store=Recorder()))
    assert err.kind is Kind.NOT_FOUND and calls == []


def test_a_private_dataset_is_invisible_to_a_teammate(world, registry):
    plant_golden(world)  # the dataset is private to its creator, the workspace owner
    member = registry.register(prefix="member")
    join(world.owner, member)
    member_principal = Principal(member.user_id, member.tenant_id, "owner", AUTH_JWT, False)
    err = refused(lambda: rs.search(member_principal, scope_of(world, "normal"), body_of(world), world.embed_settings, doc_store=world.store(), embedder=planted_query))
    assert err.kind is Kind.NOT_FOUND


def test_a_dataset_of_another_workspace_the_caller_belongs_to_is_refused_for_this_scope(world, registry, fake):
    """The scope names the acting workspace; a dataset of another workspace is the one not-found even for a member of both."""
    other = make_pipeline_world(registry, fake)
    join(other.owner, world.owner)
    team = kb.create_dataset(other.settings, ActingScope(other.owner.tenant_id, "owner", "owner"), other.owner.user_id, kb.CreateRequest(name=f"team-{uuid.uuid4().hex[:6]}", permission="team"))
    err = refused(lambda: ask(world, body_of(world, dataset_ids=[team.id])))
    assert err.kind is Kind.NOT_FOUND


def test_datasets_with_different_embedding_models_are_refused(world):
    other_model = world.dataset.embd_id.replace("fake-embed", "fake-filter")
    assert other_model != world.dataset.embd_id
    second = kb.create_dataset(world.settings, scope_of(world), world.owner.user_id, kb.CreateRequest(name=f"mixed-{uuid.uuid4().hex[:6]}", embd_id=other_model))
    err = refused(lambda: ask(world, body_of(world, dataset_ids=[world.dataset.id, second.id])))
    assert err.kind is Kind.INVALID and err.reason == "embedding_mismatch"


# ----------------------------------------------------------------------------- validation


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"question": "   "}, "question_invalid"),
        ({"question": "x" * 2001}, "question_invalid"),
        ({"question": 7}, "question_invalid"),
        ({"dataset_ids": []}, "fields_invalid"),
        ({"dataset_ids": ["not-an-id"]}, "fields_invalid"),
        ({"dataset_ids": ["a" * 32] * 2}, "fields_invalid"),
        ({"dataset_ids": [uuid.uuid4().hex for _ in range(11)]}, "fields_invalid"),
        ({"similarity_threshold": 1.5}, "fields_invalid"),
        ({"similarity_threshold": float("nan")}, "fields_invalid"),
        ({"vector_similarity_weight": -0.1}, "fields_invalid"),
        ({"top_k": 15}, "fields_invalid"),
        ({"top_k": 10**6}, "fields_invalid"),
        ({"page": 0}, "fields_invalid"),
        ({"size": 101}, "fields_invalid"),
        ({"size": True}, "fields_invalid"),
        ({"fusion": "bm25"}, "fields_invalid"),
        ({"doc_ids": ["nope"]}, "ids_invalid"),
    ],
)
def test_a_bad_body_is_a_typed_400_before_anything_runs(world, overrides, reason):
    err = refused(lambda: ask(world, body_of(world, **overrides), embedder=lambda _t: pytest.fail("the provider must not be called")))
    assert err.kind is Kind.INVALID and err.reason == reason


def test_the_error_text_never_holds_the_question(world):
    secret_question = "ultra-private-question-text " + "y" * 2100
    err = refused(lambda: ask(world, body_of(world, question=secret_question)))
    assert "ultra-private" not in err.message and "ultra-private" not in str(err)


# ----------------------------------------------------------------------------- failure mapping and finite numbers


def test_an_index_outage_is_index_unavailable(world):
    class Down:
        def search(self, *a, **kw):
            raise DocStoreError("search")

    err = refused(lambda: ask(world, body_of(world), doc_store=Down()))
    assert err.kind is Kind.UNAVAILABLE and err.reason == "index_unavailable"


def test_non_finite_numbers_never_reach_the_view(world):
    plant_golden(world)
    real = world.store()

    class Poisoned:
        def search(self, *args, **kwargs):
            found = real.search(*args, **kwargs)
            for hit in found.hits:
                if "content_with_weight" in hit:
                    hit["position_int"] = [[1, 0, 0, 1, 1]]
                    hit["page_dims_flt"] = [[1, float("nan"), float("inf")]]
            return SearchResult(found.total, found.hits, found.aggregations)

        def __getattr__(self, name):
            return getattr(real, name)

    view = ask(world, body_of(world), doc_store=Poisoned())
    assert view["chunks"] and all(c["page_sizes"] == {"1": [None, None]} for c in view["chunks"])
    json.dumps(view, allow_nan=False)


# ----------------------------------------------------------------------------- the provider


def test_one_call_spends_one_embedding_request_and_the_key_stays_out_of_the_view(world, fake):
    plant_golden(world)
    before = len(fake.hits(EMBEDDINGS))
    view = rs.search(principal_of(world.owner), scope_of(world), body_of(world), world.embed_settings, doc_store=world.store())
    assert len(fake.hits(EMBEDDINGS)) - before == 1
    assert world.api_key not in json.dumps(view)


def test_a_refusing_provider_is_a_typed_error_not_a_key_leak(world, fake):
    plant_golden(world)
    fake.embed_mode = "refuse"
    err = refused(lambda: rs.search(principal_of(world.owner), scope_of(world), body_of(world), world.embed_settings, doc_store=world.store()))
    assert err.kind is not Kind.NOT_FOUND and world.api_key not in err.message and world.api_key not in str(err)


# ----------------------------------------------------------------------------- the rate limit


def test_the_per_workspace_and_user_limit_answers_rate_limited_with_retry_after(world):
    plant_golden(world)
    cfg = dataclasses.replace(world.settings, retrieval=dataclasses.replace(world.settings.retrieval, rate_max=2, rate_window_seconds=60))  # real hosts: the guard talks to the real Valkey
    key = f"retrieval:{world.owner.tenant_id}:{world.owner.user_id}"
    rd = world.settings.redis
    raw = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db)
    try:
        for _ in range(2):
            rs.retrieval_rate_guard(cfg, world.owner.tenant_id, world.owner.user_id)
        err = refused(lambda: rs.retrieval_rate_guard(cfg, world.owner.tenant_id, world.owner.user_id))
        assert err.kind is Kind.RATE_LIMITED and err.reason == "rate_limited" and err.retry_after and err.retry_after > 0
        rs.retrieval_rate_guard(cfg, world.owner.tenant_id, "another-user")  # a different user has a window of their own
        raw.delete(key, f"retrieval:{world.owner.tenant_id}:another-user")
    finally:
        raw.close()


def test_an_unreachable_counter_store_refuses(world):
    closed = dataclasses.replace(world.settings, redis=dataclasses.replace(world.settings.redis, host="127.0.0.1", port=1))
    err = refused(lambda: rs.retrieval_rate_guard(closed, world.owner.tenant_id, world.owner.user_id))
    assert err.kind is Kind.UNAVAILABLE and err.reason == "busy"


# ----------------------------------------------------------------------------- the optional rerank stage (plan 05-05)

RERANK_PATH = "/api/v1/rerank"
RERANK_ID = "fake-rerank@OpenRouter"


def seed_rerank(world: World, owner=None) -> None:
    """Save an OpenRouter-style rerank model pair on the fake provider's rerank path for ``owner``'s workspace."""
    owner = owner or world.owner
    structure.save_instance(
        world.settings.llm, owner.tenant_id, "OpenRouter", "default", api_key="-".join(("sk", "fake", uuid.uuid4().hex[:20])), api_base=f"{world.fake.root}/api/v1",
        api_version=None, models=[NewModel("fake-rerank", "rerank", None, 8192), NewModel("fake-rerank-500", "rerank", None, 8192)], replace_key=True,
    )  # fmt: skip


def with_cap(world: World, cap: int):
    return dataclasses.replace(world.embed_settings, retrieval=dataclasses.replace(world.embed_settings.retrieval, rerank_max_candidates=cap))


def test_without_a_rerank_id_the_order_is_the_fusion_order_and_no_rerank_request_is_made(world, fake):
    plant_golden(world)
    seed_rerank(world)
    view = ask(world, body_of(world, vector_similarity_weight=1))
    assert kinds_of_ids(view) == ["s", "k"] and view["rerank_applied"] is False
    assert all("rerank_similarity" not in c for c in view["chunks"]) and view["timings"]["rerank_ms"] == 0.0
    assert fake.hits(RERANK_PATH) == []


def test_a_rerank_model_reorders_the_candidates_through_one_real_http_call(world, fake):
    plant_golden(world)
    seed_rerank(world)
    view = ask(world, body_of(world, vector_similarity_weight=1, rerank_id=RERANK_ID))
    assert kinds_of_ids(view) == ["k", "s"], "the rerank order differs from the fusion order"
    assert view["rerank_applied"] is True and view["timings"]["rerank_ms"] > 0
    assert [c["rerank_similarity"] for c in view["chunks"]] == pytest.approx([1.0, 0.0])
    (call,) = fake.hits(RERANK_PATH)
    assert call.body["model"] == "fake-rerank" and call.body["query"] == RARE_KEYWORD and sorted(call.body["documents"]) == sorted([K_TEXT, S_TEXT])
    assert world.api_key not in json.dumps(view)
    json.dumps(view, allow_nan=False)


def test_the_rerank_request_carries_at_most_the_candidate_cap(world, fake):
    doc_id = add_document(world, "many.txt", b"many body")
    for index in range(12):
        plant(world, world.dataset, doc_id, f"m{index:02d}-{doc_id[:6]}", f"{RARE_KEYWORD} passage number {index}", index % DIMENSION)
    seed_rerank(world)
    view = ask(world, body_of(world, rerank_id=RERANK_ID), settings=with_cap(world, 8))
    (call,) = fake.hits(RERANK_PATH)
    assert len(call.body["documents"]) == 8
    assert view["rerank_applied"] is True and view["total"] <= 8


def test_a_failing_rerank_model_is_a_502_with_no_partial_result(world, fake):
    plant_golden(world)
    seed_rerank(world)
    err = refused(lambda: ask(world, body_of(world, rerank_id="fake-rerank-500@OpenRouter")))
    assert (err.kind, err.reason) == (Kind.BAD_GATEWAY, "rerank_unavailable")
    assert len(fake.hits(RERANK_PATH)) == 1, "one call, no retry on a plain 500"
    assert world.api_key not in err.message


@pytest.mark.parametrize("bad", [lambda q, t: [0.1], lambda q, t: (_ for _ in ()).throw(RuntimeError("boom"))])
def test_a_reranker_that_breaks_is_the_same_typed_failure(world, bad):
    plant_golden(world)
    err = refused(lambda: ask(world, body_of(world, rerank_id="any@OpenRouter"), reranker=bad))
    assert (err.kind, err.reason) == (Kind.BAD_GATEWAY, "rerank_unavailable")
    assert "boom" not in err.message


def test_an_unknown_or_overlong_rerank_id_is_model_unavailable_and_spends_no_embedding(world, fake):
    plant_golden(world)
    before = len(fake.hits(EMBEDDINGS))
    for rerank_id in ("missing@OpenRouter", "fake-rerank@NoSuchProvider", "not a model id", "x" * 129):
        err = refused(lambda: rs.search(principal_of(world.owner), scope_of(world), body_of(world, rerank_id=rerank_id), world.embed_settings, doc_store=world.store()))
        assert (err.kind, err.reason) == (Kind.CONFLICT, "model_unavailable"), rerank_id
    assert len(fake.hits(EMBEDDINGS)) == before and fake.hits(RERANK_PATH) == []


def test_a_chat_model_id_cannot_be_used_as_a_rerank_model(world):
    plant_golden(world)
    structure.save_instance(
        world.settings.llm, world.owner.tenant_id, "OpenRouter", "default", api_key="-".join(("sk", "fake", uuid.uuid4().hex[:20])), api_base=world.fake.base_url,
        api_version=None, models=[NewModel("fake-chat", "chat", None, 8192)], replace_key=True,
    )  # fmt: skip
    err = refused(lambda: ask(world, body_of(world, rerank_id="fake-chat@OpenRouter")))
    assert (err.kind, err.reason) == (Kind.CONFLICT, "model_unavailable")


def test_another_workspaces_rerank_model_is_model_unavailable(world, registry, fake):
    plant_golden(world)
    stranger = registry.register(prefix="rrstr")
    seed_rerank(world, stranger)
    err = refused(lambda: ask(world, body_of(world, rerank_id=RERANK_ID)))
    assert (err.kind, err.reason) == (Kind.CONFLICT, "model_unavailable") and fake.hits(RERANK_PATH) == []


@pytest.mark.parametrize("bad", [5, "", "   ", ["a"]])
def test_a_malformed_rerank_id_is_a_fields_error(world, bad):
    err = refused(lambda: ask(world, body_of(world, rerank_id=bad), embedder=lambda _t: pytest.fail("the provider must not be called")))
    assert err.kind is Kind.INVALID and err.reason == "fields_invalid"
