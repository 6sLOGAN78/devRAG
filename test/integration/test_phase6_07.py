"""Real infrastructure and public Go catalog; no selected case skips prerequisites."""

import json
import httpx
import pytest
from test.helpers.accounts import AccountRegistry
from test.testcases.conftest import BASE_URL
from test.integration import test_pipeline_failures as pipeline_tests

_bound_database = pipeline_tests._bound_database
registry = pipeline_tests.registry
fake = pipeline_tests.fake
world = pipeline_tests.world
from test.helpers.ingest import add_document, add_task, run_task, indexed, paragraphs
from test.helpers.uploads import sql

pytestmark = pytest.mark.integration


def test_actual_public_go_templates_are_credential_independent_and_finite():
    accounts = AccountRegistry(BASE_URL)
    try:
        owner = accounts.register(prefix="catalog")
        with httpx.Client(base_url=BASE_URL, timeout=30) as client:
            for path in ["/api/v1/pipelines?type=builtin", "/api/v1/pipelines/one"]:
                baseline = client.get(path)
                assert baseline.status_code == 200, "public Go catalog is missing"
                assert baseline.headers.get("x-api-source") == "go"
                for value in [owner.token, "invalid-catalog-credential"]:
                    result = client.get(path, headers={"Authorization": f"Bearer {value}"})
                    assert result.content == baseline.content and result.status_code == 200
                assert client.post(path).status_code == 401
            items = client.get("/api/v1/pipelines?type=builtin").json()["data"]
            assert len(items) == 14
            from rag.chunking.factory import available, METHODS

            assert [t["id"] for t in items] == list(METHODS)
            assert all(t["available"] == available(t["parser_id"]) for t in items)
            assert all(set(t) == {"id", "name", "description", "parser_id", "parser_config", "available"} for t in items)
            assert client.get("/api/v1/pipelines?type=private").status_code == 400
            assert client.get("/api/v1/pipelines/unknown").json() == {"code": 404, "message": "not found", "data": None}
            assert client.get("/api/v1/pipelines/other").content == client.get("/api/v1/pipelines/unknown").content
            assert client.get("/api/v1/pipelines/one/private").status_code == 401
    finally:
        accounts.cleanup()


def test_actual_worker_one_chunk_does_not_apply_general_budget(world, fake):
    source = paragraphs(4, tokens=300)
    doc = add_document(world, "whole.txt", source)
    sql("UPDATE `document` SET `parser_id`=%s, `parser_config`=%s WHERE `id`=%s", ("one", json.dumps({"chunk_token_num": 1}), doc))
    expected = "\n".join(source.decode().split("\n\n"))
    fake.reset()
    result = run_task(world, add_task(doc))
    assert result.chunk_count == 1
    rows = indexed(world, doc_id=[doc])
    assert len(rows) == 1
    assert rows[0]["content_with_weight"] == expected
    calls = [r for r in fake.requests if r.path == "/v1/embeddings"]
    assert len(calls) == 1 and calls[0].body["input"] == [expected]


def test_actual_worker_refuses_oversize_one_without_any_embedding_request(world, fake):
    from rag.svr.failure import TaskFailure

    source = paragraphs(30, tokens=300)
    doc = add_document(world, "oversize-whole.txt", source)
    sql("UPDATE `document` SET `parser_id`=%s WHERE `id`=%s", ("one", doc))
    fake.reset()
    with pytest.raises(TaskFailure) as failure:
        run_task(world, add_task(doc))
    assert failure.value.code == "chunk_too_long" and failure.value.terminal
    assert fake.hits("/v1/embeddings") == []
    assert indexed(world, doc_id=[doc]) == []
