"""The live_model ingestion tier: a real document becomes real, correctly placed vectors (plan 04-33).

E2E-05, E2E-06, IDX-01, IDX-02, IDX-03, IDX-07, CHUNK-16, CHUNK-19, CHUNK-20, ING-13, TEST-11; D-03, D-04, D-11, D-16, D-17, D-22, D-23.

Everything is real: the provider is saved through the product API with the user's OpenRouter key, the 13-page PDF and five small files go through
Nginx, the app, the queue, the task-executor container, the real ``baai/bge-m3`` embedding model and the real Elasticsearch index. The tier is tiny
on purpose (D-16): the PDF's ``chunk_token_num`` is set from its longest line so it makes about 26 chunks, the five small files make about 5 each,
and the whole file embeds at most 72 chunks, asserted from the index counts and not from provider calls.

The key is read only by ``stack_env()`` and travels only in the provider PUT body. No assertion message, f-string or print below contains it:
results are reduced to booleans and counts before they are asserted. Without the key the file fails outright with the fixed message (D-04).
"""

# ruff: noqa: F811  (fixtures imported by name are re-requested as arguments)
from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from api.db.services.llm_service import LLMBundle
from common.doc_store.doc_store_base import MatchDenseExpr, index_name
from common.settings import Settings, load_settings
from rag.utils.es_conn import get_doc_store
from test.conftest import stack_env
from test.helpers.accounts import Account
from test.helpers.doc_store_contract import search
from test.helpers.ingest import (
    TABLE_ROW,
    chunk_texts,
    dataset_row,
    doc_row,
    expected_pdf_chunks,
    index_count,
    pdf_chunk_config,
    poison_docx,
    small_live_files,
    start_parse,
    task_rows,
    thirteen_page_pdf,
    upload_text,
    wait_run,
)
from test.testcases.conftest import compose
from test.testcases.test_live_models import (  # noqa: F401  (fixtures are used by name)
    DATASETS,
    DEFAULTS,
    PROVIDER,
    PROVIDERS,
    LiveEnv,
    Recorder,
    bound_database,
    bundle_settings,
    call,
    client,
    data_of,
    ingress,
    leaks,
    live_env,
    owner,
    recorder,
    sql,
    started_at,
    used_tokens,
)

pytestmark = pytest.mark.live_model

MISSING_KEY_MESSAGE = "OPENROUTER_API_KEY is missing from docker/.env; the Phase 3 gate fails without it (D-04)"
CHUNK_CAP = 72
MIME = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".html": "text/html",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
EDITED_TEXT = "Nebula cartographers charted the amber lighthouse archive beneath glacier tides"
ADDED_TEXT = "Copper falcons memorised the harbour almanac of drifting orchard clocks"
STATE: dict[str, Any] = {"embedded": 0}
EVIDENCE: list[str] = []


def suffix_of(name: str) -> str:
    return "." + name.rsplit(".", 1)[1]


def pdf_name() -> str:
    return "live-thirteen.pdf"


def chunks_path(dataset_id: str, doc_id: str, chunk_id: str | None = None) -> str:
    base = f"{DATASETS}/{dataset_id}/documents/{doc_id}/chunks"
    return base if chunk_id is None else f"{base}/{chunk_id}"


def vector_field(live: LiveEnv) -> str:
    return f"q_{live.dimension}_vec"


def api(http: httpx.Client, method: str, path: str, token: str, *, body: Any = None, params: dict[str, str] | None = None) -> httpx.Response:
    http.cookies.clear()
    response = http.request(method, path, headers={"Authorization": f"Bearer {token}"}, json=body, params=params, timeout=60.0)
    assert response.headers.get("x-api-source") == "python", (method, path, response.status_code)
    return response


@pytest.fixture(scope="module", autouse=True)
def key_present() -> None:
    """The fixed failure of the model tier, raised before the stack wait or any network use (D-04)."""
    if not stack_env().get("OPENROUTER_API_KEY", "").strip():
        pytest.fail(MISSING_KEY_MESSAGE)


@pytest.fixture(scope="module")
def settings(live_env: LiveEnv) -> Settings:
    return load_settings()


@pytest.fixture(scope="module")
def workspace(client: httpx.Client, owner: Account, live_env: LiveEnv) -> SimpleNamespace:
    """The OpenRouter provider saved through the API (the app container makes the test calls), the default embedding model and one dataset."""
    models = [{"name": live_env.embed_model, "type": "embedding"}]
    saved = data_of(call(client, "PUT", PROVIDERS, owner.token, {"provider": PROVIDER, "api_key": live_env.key, "models": models}))
    assert saved["configured"] is True
    data_of(call(client, "PATCH", DEFAULTS, owner.token, {"embedding": live_env.embed_id}))
    dataset = data_of(call(client, "POST", DATASETS, owner.token, {"name": "Live ingestion knowledge base"}))
    assert dataset["embd_id"] == live_env.embed_id and dataset["embedding_dimension"] == live_env.dimension
    return SimpleNamespace(dataset_id=dataset["id"])


@pytest.fixture(scope="module")
def journey(client: httpx.Client, owner: Account, live_env: LiveEnv, workspace: SimpleNamespace, settings: Settings) -> SimpleNamespace:
    """Upload the PDF and the five small files, set the PDF's chunk budget, parse all six with one request and wait for all of them."""
    dataset_id = workspace.dataset_id
    before = used_tokens_or_zero(owner.tenant_id, live_env.embed_model)
    docs: dict[str, dict[str, Any]] = {}
    pdf = upload_text(client, owner, dataset_id, thirteen_page_pdf(), pdf_name(), mime=MIME[".pdf"])
    docs[pdf_name()] = pdf
    small = small_live_files()
    for name, (data, _) in small.items():
        docs[name] = upload_text(client, owner, dataset_id, data, name, mime=MIME[suffix_of(name)])
    patched = api(client, "PATCH", f"{DATASETS}/{dataset_id}/documents/{pdf['id']}", owner.token, body={"parser_config": pdf_chunk_config()})
    assert patched.status_code == 200 and patched.json()["code"] == 0
    started = start_parse(client, owner, dataset_id, [d["id"] for d in docs.values()])
    assert started.status_code == 200 and started.json()["code"] == 0
    deadline_rows = {}
    for name, doc in docs.items():
        deadline_rows[name] = wait_run(client, owner, dataset_id, doc["id"], "3", timeout=300)
    return SimpleNamespace(docs=docs, rows=deadline_rows, small=small, before_tokens=before, dataset_id=dataset_id)


def used_tokens_or_zero(tenant_id: str, model: str) -> int:
    rows = sql("SELECT `used_tokens` FROM `tenant_llm` WHERE `tenant_id` = %s AND `llm_name` = %s", (tenant_id, model))
    return int(rows[0][0]) if rows else 0


def stored_vectors(settings: Settings, live: LiveEnv, tenant_id: str, dataset_id: str, doc_id: str) -> list[list[float]]:
    result = search(
        get_doc_store(settings),
        index_name(tenant_id),
        [dataset_id],
        condition={"doc_id": [doc_id]},
        select=[vector_field(live)],
        limit=100,
    )
    return [list(hit[vector_field(live)]) for hit in result.hits]


def nearest(settings: Settings, live: LiveEnv, owner: Account, dataset_id: str, text: str) -> list[dict[str, Any]]:
    """The three nearest chunks of the dataset to the real embedding of ``text``.

    The kNN asks for 32 neighbours (64 HNSW candidates, the adapter's 2k rule, as in the reference) and keeps the first three:
    with k=3 the approximate search had only 6 candidates and could miss an exact match written moments before.
    """
    llm = LLMBundle(owner.tenant_id, live.embed_id, "embedding", settings=bundle_settings(live), expected_dimension=live.dimension)
    query, _ = llm.encode_queries(text)
    near = MatchDenseExpr(vector_field(live), query, "float", "cosine", 32)
    result = search(
        get_doc_store(settings),
        index_name(owner.tenant_id),
        [dataset_id],
        matches=[near],
        limit=3,
        select=["doc_id", "page_num_int", "content_with_weight"],
    )
    return list(result.hits)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


# --- the missing-key failure -------------------------------------------------------------------------------------------


def test_the_fixed_failure_message_is_the_one_of_the_model_tier() -> None:
    from test.testcases import test_live_models

    assert MISSING_KEY_MESSAGE == test_live_models.MISSING_KEY_MESSAGE


# --- the journey -------------------------------------------------------------------------------------------------------


def test_the_pdf_and_five_small_files_finish_with_chunk_counts_equal_to_the_index(client: httpx.Client, owner: Account, live_env: LiveEnv, settings: Settings, journey: SimpleNamespace) -> None:
    pdf = journey.docs[pdf_name()]
    pdf_count = index_count(settings, owner.tenant_id, journey.dataset_id, pdf["id"])
    expected = expected_pdf_chunks()
    assert pdf_count == expected and 20 <= pdf_count <= 40, "the PDF count equals the offline count and lies in the bounded range"
    assert journey.rows[pdf_name()]["chunk_count"] == pdf_count
    total = pdf_count
    for name, (_, offline) in journey.small.items():
        count = index_count(settings, owner.tenant_id, journey.dataset_id, journey.docs[name]["id"])
        assert count == journey.rows[name]["chunk_count"] == offline and count <= 10, name
        total += count
    STATE["embedded"] = total
    STATE["pdf_count"] = pdf_count
    assert total <= CHUNK_CAP
    dataset = dataset_row(client, owner, journey.dataset_id)
    assert dataset["chunk_num"] == total and dataset["doc_num"] == 6
    EVIDENCE.append(f"pdf_chunks={pdf_count} expected={expected} " + " ".join(f"{n}={c}" for n, c in _counts(journey, settings, owner)) + f" total={total}")


def _counts(journey: SimpleNamespace, settings: Settings, owner: Account) -> list[tuple[str, int]]:
    return [(n, index_count(settings, owner.tenant_id, journey.dataset_id, journey.docs[n]["id"])) for n in journey.small]


def test_the_pdf_has_two_task_rows_and_positions_on_all_thirteen_pages(client: httpx.Client, owner: Account, journey: SimpleNamespace) -> None:
    pdf_id = journey.docs[pdf_name()]["id"]
    rows = sql("SELECT `from_page`, `to_page` FROM `task` WHERE `doc_id` = %s ORDER BY `from_page`", (pdf_id,))
    assert [(int(a), int(b)) for a, b in rows] == [(0, 12), (12, 13)]
    chunks = chunk_texts(api, client, owner.token, journey.dataset_id, pdf_id)
    assert {p["page"] for c in chunks for p in c["positions"]} == set(range(1, 14))


def test_every_stored_vector_is_1024_long_and_unit_length(owner: Account, live_env: LiveEnv, settings: Settings, journey: SimpleNamespace) -> None:
    total = 0
    bad_length = bad_norm = 0
    for doc in journey.docs.values():
        vectors = stored_vectors(settings, live_env, owner.tenant_id, journey.dataset_id, doc["id"])
        total += len(vectors)
        bad_length += sum(1 for v in vectors if len(v) != live_env.dimension)
        bad_norm += sum(1 for v in vectors if abs(math.sqrt(sum(x * x for x in v)) - 1.0) > 1e-6)
    assert total == STATE["embedded"], "every chunk has a vector"
    assert bad_length == 0 and bad_norm == 0


def test_a_page_seven_sentence_finds_the_chunk_that_holds_it(owner: Account, live_env: LiveEnv, settings: Settings, journey: SimpleNamespace, gc_at_loop_teardown: None) -> None:
    hits = nearest(settings, live_env, owner, journey.dataset_id, "Page 7 line 3 alpha")
    assert hits, "the search answered"
    top = hits[0]
    assert top["doc_id"] == journey.docs[pdf_name()]["id"], "the nearest chunk is a PDF chunk"
    assert 7 in top["page_num_int"] and "Page 7 line 3 alpha" in top["content_with_weight"]


def test_a_docx_table_sentence_finds_the_chunk_that_holds_it(owner: Account, live_env: LiveEnv, settings: Settings, journey: SimpleNamespace, gc_at_loop_teardown: None) -> None:
    hits = nearest(settings, live_env, owner, journey.dataset_id, " ".join(TABLE_ROW))
    assert hits and hits[0]["doc_id"] == journey.docs["live-report.docx"]["id"]
    assert TABLE_ROW[0] in hits[0]["content_with_weight"]


def test_token_usage_is_recorded_and_the_totals_equal_the_index(client: httpx.Client, owner: Account, live_env: LiveEnv, settings: Settings, journey: SimpleNamespace) -> None:
    assert journey.before_tokens == 0
    after = used_tokens(owner.tenant_id, live_env.embed_model)
    assert after > journey.before_tokens, "used_tokens grew"
    dataset = dataset_row(client, owner, journey.dataset_id)
    summed = sum(doc_row(client, owner, journey.dataset_id, d["id"])["chunk_count"] for d in journey.docs.values())
    assert dataset["chunk_num"] == summed == STATE["embedded"]
    EVIDENCE.append(f"used_tokens_after_parse={after}")


# --- edit, add and re-parse -------------------------------------------------------------------------------------------


def test_an_edit_and_an_add_embed_with_the_real_model_and_a_confirmed_reparse_restores_the_count(
    client: httpx.Client, owner: Account, live_env: LiveEnv, settings: Settings, journey: SimpleNamespace, gc_at_loop_teardown: None
) -> None:
    txt = journey.docs["live-notes.txt"]
    dataset_id, doc_id = journey.dataset_id, txt["id"]
    original = journey.small["live-notes.txt"][1]
    listed = chunk_texts(api, client, owner.token, dataset_id, doc_id)
    target = listed[0]["id"]
    store = get_doc_store(settings)
    before = store.get(target, index_name(owner.tenant_id), [dataset_id])
    assert before is not None
    old_vector = list(before[vector_field(live_env)])

    changed = data_of(api(client, "PATCH", chunks_path(dataset_id, doc_id, target), owner.token, body={"content_with_weight": EDITED_TEXT}))
    STATE["embedded"] += 1
    assert changed["origin"] == "edited" and changed["id"] == target
    after = store.get(target, index_name(owner.tenant_id), [dataset_id])
    assert after is not None and after["content_with_weight"] == EDITED_TEXT
    new_vector = list(after[vector_field(live_env)])
    assert len(new_vector) == live_env.dimension and cosine(old_vector, new_vector) < 0.999999
    assert nearest(settings, live_env, owner, dataset_id, EDITED_TEXT)[0]["content_with_weight"] == EDITED_TEXT

    added = data_of(api(client, "POST", chunks_path(dataset_id, doc_id), owner.token, body={"content_with_weight": ADDED_TEXT}))
    STATE["embedded"] += 1
    top = nearest(settings, live_env, owner, dataset_id, ADDED_TEXT)[0]
    assert top["content_with_weight"] == ADDED_TEXT
    assert store.get(added["id"], index_name(owner.tenant_id), [dataset_id]) is not None

    refused = start_parse(client, owner, dataset_id, [doc_id])
    reason = (refused.json().get("data") or {}).get("reason")
    entry = (refused.json().get("data") or {}).get("documents", [{}])[0]
    assert refused.status_code == 409 and reason == "confirm_required"
    assert entry["edited_count"] == 1 and entry["manual_count"] == 1

    assert start_parse(client, owner, dataset_id, [doc_id], confirm=True).status_code == 200
    STATE["embedded"] += original
    wait_run(client, owner, dataset_id, doc_id, "3", timeout=300)
    again = chunk_texts(api, client, owner.token, dataset_id, doc_id)
    assert len(again) == original and {c["origin"] for c in again} == {"parsed"}
    assert index_count(settings, owner.tenant_id, dataset_id, doc_id) == original


# --- the poison file ---------------------------------------------------------------------------------------------------


def test_a_damaged_docx_fails_with_file_damaged_and_costs_no_provider_call(client: httpx.Client, owner: Account, live_env: LiveEnv, workspace: SimpleNamespace, journey: SimpleNamespace) -> None:
    doc = upload_text(client, owner, workspace.dataset_id, poison_docx(), "live-damaged.docx", mime=MIME[".docx"])
    tokens_before = used_tokens(owner.tenant_id, live_env.embed_model)
    assert start_parse(client, owner, workspace.dataset_id, [doc["id"]]).status_code == 200
    row = wait_run(client, owner, workspace.dataset_id, doc["id"], "4", timeout=180)
    assert row["error"]["code"] == "file_damaged"
    (task_id,) = task_rows(doc["id"])
    retries = sql("SELECT `retry_count` FROM `task` WHERE `id` = %s", (task_id,))
    assert int(retries[0][0]) == 3
    assert used_tokens(owner.tenant_id, live_env.embed_model) == tokens_before, "the damaged file made no provider call"
    STATE["poison_doc"] = doc["id"]


# --- the budget and the leak scan -------------------------------------------------------------------------------------


def test_the_embedded_chunks_stay_within_the_cap(journey: SimpleNamespace) -> None:
    assert STATE["embedded"] <= CHUNK_CAP, "at most 72 embedded chunks for the whole file (D-16)"
    EVIDENCE.append(f"embedded_chunks_total={STATE['embedded']}/{CHUNK_CAP}")


def test_no_response_progress_line_log_row_or_container_log_contains_the_key(live_env: LiveEnv, owner: Account, recorder: Recorder, started_at: str, journey: SimpleNamespace) -> None:
    assert recorder.captured, "responses were recorded"
    response_hits = sum(leaks(text, live_env.key) for text in recorder.captured)
    assert response_hits == 0, "the key or a window of it appears in a response"

    doc_ids = [d["id"] for d in journey.docs.values()] + ([STATE["poison_doc"]] if "poison_doc" in STATE else [])
    marks = ", ".join(["%s"] * len(doc_ids))
    progress = sql(f"SELECT `progress_msg` FROM `task` WHERE `doc_id` IN ({marks})", tuple(doc_ids))  # noqa: S608 - placeholders only
    progress_hits = sum(leaks(str(r[0] or ""), live_env.key) for r in progress)
    assert progress and progress_hits == 0, "the key appears in a task progress line"
    log_rows = sql("SELECT `progress_msg`, `dsl` FROM `pipeline_operation_log` WHERE `tenant_id` = %s", (owner.tenant_id,))
    row_hits = sum(leaks(f"{r[0]} {r[1]}", live_env.key) for r in log_rows)
    assert log_rows and row_hits == 0, "the key appears in an ingestion log row"

    executor = compose("logs", "--no-color", "--since", started_at, "task-executor")
    app = compose("logs", "--no-color", "--since", started_at, "app")
    assert executor.returncode == 0 and app.returncode == 0
    assert executor.stdout.strip() != "", "the scan read the executor logs"
    container_hits = leaks(executor.stdout + executor.stderr + app.stdout + app.stderr, live_env.key)
    assert container_hits == 0, "the key appears in a container log"
    EVIDENCE.append(f"leak scan: responses={len(recorder.captured)} progress_lines={len(progress)} log_rows={len(log_rows)} hits=0")
    for line in EVIDENCE:
        print("LIVE-EVIDENCE", line)
