"""Actual structured parser/QA/provider/index path and refusals."""

import json
import pytest
from test.integration import test_pipeline_failures as base
from test.helpers.ingest import add_document, add_task, run_task, indexed
from test.helpers.uploads import sql
from test.helpers.doc_store_contract import search
from common.doc_store.doc_store_base import MatchTextExpr

_bound_database = base._bound_database
registry = base.registry
fake = base.fake
world = base.world
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("suffix", ["csv", "json", "xlsx", "txt"])
def test_real_qa_pair_values_question_index_and_field_search(world, fake, repo_root, suffix):
    root = repo_root / "test/fixtures/phase6"
    gold = json.loads((root / "qa-original-annotation.json").read_text())
    doc = add_document(world, "qa-original." + suffix, (root / ("qa-original." + suffix)).read_bytes())
    sql("UPDATE `document` SET `parser_id`=%s WHERE `id`=%s", ("qa", doc))
    fake.reset()
    result = run_task(world, add_task(doc))
    assert result.chunk_count == 2
    rows = sorted(indexed(world, doc_id=[doc]), key=lambda r: r["order_int"])
    assert rows[0]["question_tks"] == "what is the lighthouse height"
    assert rows[1]["question_tks"] == "what is the orchard harvest"
    assert all(answer in row["content_with_weight"] for answer, row in zip(gold["answers"], rows, strict=True))
    matches = search(world.store(), world.index, [world.dataset.id], condition={"doc_id": [doc]}, matches=[MatchTextExpr(["question_tks"], "lighthouse", 10)])
    assert len(matches.hits) == 1 and matches.hits[0]["id"] == rows[0]["id"]
    calls = fake.hits("/v1/embeddings")
    assert len(calls) == 1 and calls[0].body["input"] == [r["content_with_weight"] for r in rows]


def test_invalid_pair_refuses_before_provider_and_index(world, fake):
    from rag.svr.failure import TaskFailure

    doc = add_document(world, "bad.csv", b"Question,Answer\nWhat height?,52\n,9100\n")
    sql("UPDATE `document` SET `parser_id`=%s WHERE `id`=%s", ("qa", doc))
    fake.reset()
    with pytest.raises(TaskFailure) as failure:
        run_task(world, add_task(doc))
    assert failure.value.code == "qa_invalid" and failure.value.terminal
    assert fake.hits("/v1/embeddings") == [] and indexed(world, doc_id=[doc]) == []
