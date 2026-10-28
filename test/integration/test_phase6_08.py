"""Manual source text through the real worker, provider wire and Elasticsearch."""

import json
import pytest
from test.integration import test_pipeline_failures as base
from test.helpers.ingest import add_document, add_task, run_task, indexed
from test.helpers.uploads import sql

_bound_database = base._bound_database
registry = base.registry
fake = base.fake
world = base.world
pytestmark = pytest.mark.integration


def test_original_manual_code_and_boundaries_survive_real_index(world, fake, repo_root):
    path = repo_root / "test/fixtures/phase6/manual-original.md"
    doc = add_document(world, "manual-original.md", path.read_bytes())
    sql("UPDATE `document` SET `parser_id`=%s,`parser_config`=%s WHERE `id`=%s", ("manual", json.dumps({"chunk_token_num": 512}), doc))
    fake.reset()
    result = run_task(world, add_task(doc))
    assert result.chunk_count == 2
    rows = sorted(indexed(world, doc_id=[doc]), key=lambda r: r["order_int"])
    code = "````python\n" + path.read_text().split("````python\n", 1)[1].split("\n````", 1)[0] + "\n````\n"
    assert code in rows[0]["content_with_weight"]
    assert "| harvest | 9100 | kg |" in rows[0]["content_with_weight"]
    assert "CALIBRATION FACT" not in rows[0]["content_with_weight"]
    assert "CALIBRATION FACT: offset 73 units." in rows[1]["content_with_weight"]
    assert all(row["source_lines_int"] for row in rows)
    calls = fake.hits("/v1/embeddings")
    assert len(calls) == 1
    assert calls[0].body["input"] == [row["content_with_weight"] for row in rows]


def test_oversize_atomic_manual_group_refuses_before_any_provider_or_index_write(world, fake):
    from rag.svr.failure import TaskFailure

    body = ("# Heading\n\nFIRST FACT 52\n\n## Code\n\n```text\n" + "word " * 9000 + "\n```\n").encode()
    doc = add_document(world, "oversize-manual.md", body)
    sql("UPDATE `document` SET `parser_id`=%s WHERE `id`=%s", ("manual", doc))
    fake.reset()
    with pytest.raises(TaskFailure) as failure:
        run_task(world, add_task(doc))
    assert failure.value.code == "chunk_too_long" and failure.value.terminal
    assert fake.hits("/v1/embeddings") == []
    assert indexed(world, doc_id=[doc]) == []
