"""Every supported format parsed to chunks on the real stack, chunk shape from the configuration, field shape and refusals (plan 04-21).

PARSE-09..13, CHUNK-01, CHUNK-02, CHUNK-16, IDX-01..03, E2E-05, E2E-06, D-13, D-15, D-16. Nothing of devRag is replaced; the loopback provider is only
the third party's end of the embedding wire. Files are tiny and purpose-built, waiting is polling with a deadline.
"""
from __future__ import annotations

import math
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from common.doc_store.doc_store_base import index_name, vector_field
from common.settings import Settings, load_settings
from rag.utils.es_conn import get_doc_store
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, running_stack_fake_provider
from test.helpers.ingest import (
    build_format_files,
    chunk_texts,
    dataset_row,
    doc_row,
    index_count,
    marker_word,
    paragraph_text,
    paragraphs,
    start_parse,
    task_rows,
    upload_text,
    wait_run,
)
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create, workspace
from test.testcases.test_provider_flow import api, ok

pytestmark = pytest.mark.e2e

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64
SUFFIXES = (".txt", ".md", ".csv", ".json", ".html", ".docx", ".xlsx", ".pptx")
MIME = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".html": "text/html",
    ".csv": "text/csv",
    ".json": "application/json",
    ".md": "text/markdown",
}


def reason_of(resp: httpx.Response) -> object:
    return (resp.json().get("data") or {}).get("reason")


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
    return workspace(ingress, registry, fake, "formats")


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings()


def new_dataset(ingress: httpx.Client, who: Account, **body: object) -> str:
    return ok(create(ingress, who, **body))["id"]


def parse_and_wait(ingress: httpx.Client, who: Account, dataset_id: str, doc_id: str, timeout: float = 120.0) -> dict[str, Any]:
    resp = start_parse(ingress, who, dataset_id, [doc_id], confirm=True)
    assert resp.status_code == 200, resp.text
    return wait_run(ingress, who, dataset_id, doc_id, "3", timeout=timeout)


def stored(settings: Settings, who: Account, dataset_id: str, chunk_id: str) -> dict[str, Any]:
    found = get_doc_store(settings).get(chunk_id, index_name(who.tenant_id), [dataset_id])
    assert found is not None, chunk_id
    return found


@pytest.fixture(scope="module")
def matrix(ingress: httpx.Client, owner: Account, settings: Settings) -> SimpleNamespace:
    """One dataset with one document per format, all parsed once; ``docs[suffix]`` holds the document, the marker and the fragments."""
    dataset_id = new_dataset(ingress, owner)
    docs: dict[str, SimpleNamespace] = {}
    for suffix, (name, data, fragments) in build_format_files(marker_word("fmt")).items():
        doc = upload_text(ingress, owner, dataset_id, data, name, mime=MIME.get(suffix, "text/plain"))
        docs[suffix] = SimpleNamespace(doc=doc, name=name, fragments=fragments, marker=fragments[0])
    for suffix, item in docs.items():
        assert start_parse(ingress, owner, dataset_id, [item.doc["id"]]).status_code == 200, suffix
    for suffix, item in docs.items():
        item.row = wait_run(ingress, owner, dataset_id, item.doc["id"], "3", timeout=180)
    return SimpleNamespace(dataset_id=dataset_id, docs=docs)


# ----------------------------------------------------------------------------- the format matrix


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_each_format_parses_to_chunks_and_the_marker_is_found_by_the_keyword_filter(
    ingress: httpx.Client, owner: Account, settings: Settings, matrix: SimpleNamespace, suffix: str
) -> None:
    item = matrix.docs[suffix]
    doc_id = item.doc["id"]
    assert item.row["run"] == "3" and item.row["chunk_count"] > 0
    assert item.row["chunk_count"] == index_count(settings, owner.tenant_id, matrix.dataset_id, doc_id), "the document counter equals the index"
    hits = chunk_texts(api, ingress, owner.token, matrix.dataset_id, doc_id, keywords=item.marker)
    assert hits, f"the keyword filter found nothing for {suffix}"
    assert item.marker in " ".join(h["text"] for h in hits)
    everything = " ".join(c["text"] for c in chunk_texts(api, ingress, owner.token, matrix.dataset_id, doc_id))
    for fragment in item.fragments:
        assert fragment in everything, (suffix, fragment)
    if suffix == ".html":
        assert "<" not in everything and "hostilescript" not in everything and "alert" not in everything, "markup and script text never reach a chunk (T-04-21-01)"
    if suffix == ".docx":
        assert "cellbody" in everything and "cellhead" in everything, "table cell text is in the chunks"
    if suffix == ".xlsx":
        assert any("headone" in c["text"] and f"{item.marker} a" in c["text"] for c in chunk_texts(api, ingress, owner.token, matrix.dataset_id, doc_id)), (
            "the header row text sits in a chunk together with a data value"
        )
    if suffix == ".pptx":
        assert "slide body text number 3" in everything and f"{item.marker}notes8" in everything, "slide text and notes are in the chunks"


def test_one_chunk_per_format_has_the_documented_fields_and_a_unit_vector_of_the_datasets_dimension(
    ingress: httpx.Client, owner: Account, settings: Settings, matrix: SimpleNamespace
) -> None:
    dimension = dataset_row(ingress, owner, matrix.dataset_id)["embedding_dimension"]
    assert isinstance(dimension, int) and dimension > 0
    for suffix, item in matrix.docs.items():
        listed = chunk_texts(api, ingress, owner.token, matrix.dataset_id, item.doc["id"])
        chunk = listed[0]
        row = stored(settings, owner, matrix.dataset_id, chunk["id"])
        assert row["id"] == chunk["id"] and row["doc_id"] == item.doc["id"] and row["kb_id"] == matrix.dataset_id, suffix
        assert row["docnm_kwd"] == item.name, suffix
        assert row["content_with_weight"] == chunk["text"] and row["content_ltks"], suffix
        assert int(row["available_int"]) == 1 and int(row["doc_enabled_int"]) == 1 and row["origin_kwd"] == "parsed", suffix
        assert row["task_id"] in task_rows(item.doc["id"]), suffix
        assert chunk["id"].rsplit("_", 1)[1] == str(row["order_int"]), "order_int equals the id suffix"
        assert int(row["token_num_int"]) > 0, suffix
        vector = row[vector_field(dimension)]
        assert len(vector) == dimension, suffix
        assert abs(math.sqrt(sum(float(v) ** 2 for v in vector)) - 1.0) < 1e-6, f"{suffix}: the stored vector is normalised"


def test_every_embedding_request_carries_at_most_sixteen_inputs(ingress: httpx.Client, owner: Account, settings: Settings, fake: FakeProvider) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(40))
    before = len(fake.requests)
    row = parse_and_wait(ingress, owner, dataset_id, doc["id"])
    assert row["chunk_count"] == 40 == index_count(settings, owner.tenant_id, dataset_id, doc["id"])
    sizes = [len(r.body.get("input", [])) for r in fake.requests[before:] if r.path == "/v1/embeddings" and isinstance(r.body, dict)]
    assert sizes and max(sizes) <= 16, sizes
    assert sum(sizes) >= 40, "all forty chunks were embedded in those requests"


# ----------------------------------------------------------------------------- the dataset's chunk configuration


def token_counts(settings: Settings, who: Account, dataset_id: str, chunks: list[dict[str, Any]]) -> list[int]:
    return [int(stored(settings, who, dataset_id, c["id"])["token_num_int"]) for c in chunks]


def test_the_datasets_token_size_and_delimiter_shape_the_chunks(ingress: httpx.Client, owner: Account, settings: Settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    ok(api(ingress, "PUT", f"/api/v1/datasets/{dataset_id}", owner.token, body={"parser_config": {"chunk_token_num": 64, "delimiter": "\n"}}))
    lines = [paragraph_text(i, 20) for i in range(30)]
    doc = upload_text(ingress, owner, dataset_id, "\n".join(lines).encode())
    parse_and_wait(ingress, owner, dataset_id, doc["id"])
    chunks = chunk_texts(api, ingress, owner.token, dataset_id, doc["id"])
    counts = token_counts(settings, owner, dataset_id, chunks)
    assert len(chunks) >= 10 and max(counts) <= 64, counts
    for chunk in chunks:
        assert len(chunk["text"].split()) > 0
    assert "".join(c["text"] for c in chunks).count("the") == "\n".join(lines).count("the"), "no text is lost"
    markers = [w for c in chunks for w in c["text"].split() if w.startswith("para")]
    assert markers == [f"para{i:04d}" for i in range(30)], "every line is kept once, in order"


def test_lines_longer_than_the_limit_never_lose_text(ingress: httpx.Client, owner: Account, settings: Settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    ok(api(ingress, "PUT", f"/api/v1/datasets/{dataset_id}", owner.token, body={"parser_config": {"chunk_token_num": 64, "delimiter": "\n"}}))
    lines = [paragraph_text(i, 90) for i in range(3)]
    doc = upload_text(ingress, owner, dataset_id, "\n".join(lines).encode())
    parse_and_wait(ingress, owner, dataset_id, doc["id"])
    chunks = chunk_texts(api, ingress, owner.token, dataset_id, doc["id"])
    counts = token_counts(settings, owner, dataset_id, chunks)
    assert len(chunks) == 6 and counts == [64, 27, 64, 27, 64, 26], counts  # each 90 token line is cut at the limit; no chunk spans two lines
    for i, line in enumerate(lines):
        rebuilt = (chunks[2 * i]["text"] + chunks[2 * i + 1]["text"]).split()
        assert rebuilt == line.split(), f"line {i} is rebuilt from its two chunks without loss or overlap"


def test_a_document_value_wins_over_the_dataset_default(ingress: httpx.Client, owner: Account, settings: Settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    ok(api(ingress, "PUT", f"/api/v1/datasets/{dataset_id}", owner.token, body={"parser_config": {"chunk_token_num": 64, "delimiter": "\n"}}))
    lines = [paragraph_text(i, 20) for i in range(30)]
    doc = upload_text(ingress, owner, dataset_id, "\n".join(lines).encode())
    changed = api(ingress, "PATCH", f"/api/v1/datasets/{dataset_id}/documents/{doc['id']}", owner.token, body={"parser_config": {"chunk_token_num": 32}})
    assert changed.status_code == 200, changed.text
    parse_and_wait(ingress, owner, dataset_id, doc["id"])
    counts = token_counts(settings, owner, dataset_id, chunk_texts(api, ingress, owner.token, dataset_id, doc["id"]))
    assert counts and max(counts) <= 32, counts


# ----------------------------------------------------------------------------- refusals


def test_a_type_without_a_parser_is_not_parseable_and_a_parse_is_refused(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, PNG, "picture.png", mime="image/png")
    row = doc_row(ingress, owner, dataset_id, doc["id"])
    assert row["parseable"] is False
    resp = start_parse(ingress, owner, dataset_id, [doc["id"]])
    assert resp.status_code == 400 and reason_of(resp) == "parse_unavailable", resp.text
    assert task_rows(doc["id"]) == [] and doc_row(ingress, owner, dataset_id, doc["id"])["run"] == "0"


def test_an_unbuilt_chunker_is_refused_everywhere_and_nothing_falls_back_to_naive(ingress: httpx.Client, owner: Account) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(3))
    patched = api(ingress, "PATCH", f"/api/v1/datasets/{dataset_id}/documents/{doc['id']}", owner.token, body={"parser_id": "qa"})
    assert patched.status_code == 400 and reason_of(patched) == "chunker_unavailable", patched.text
    put = api(ingress, "PUT", f"/api/v1/datasets/{dataset_id}", owner.token, body={"parser_id": "qa"})
    assert put.status_code == 400 and reason_of(put) == "chunker_unavailable", put.text
    assert doc_row(ingress, owner, dataset_id, doc["id"])["parser_id"] == "naive"
    assert dataset_row(ingress, owner, dataset_id)["parser_id"] == "naive"


def test_a_document_uploaded_with_an_unbuilt_chunker_is_refused_at_parse_until_changed_to_naive(ingress: httpx.Client, owner: Account, settings: Settings) -> None:
    dataset_id = new_dataset(ingress, owner)
    doc = upload_text(ingress, owner, dataset_id, paragraphs(3), params={"parser_id": "qa"})
    resp = start_parse(ingress, owner, dataset_id, [doc["id"]])
    assert resp.status_code == 400 and reason_of(resp) == "chunker_unavailable", resp.text
    assert task_rows(doc["id"]) == [] and doc_row(ingress, owner, dataset_id, doc["id"])["run"] == "0"
    fixed = api(ingress, "PATCH", f"/api/v1/datasets/{dataset_id}/documents/{doc['id']}", owner.token, body={"parser_id": "naive"})
    assert fixed.status_code == 200, fixed.text
    row = parse_and_wait(ingress, owner, dataset_id, doc["id"])
    assert row["chunk_count"] == 3 == index_count(settings, owner.tenant_id, dataset_id, doc["id"])
