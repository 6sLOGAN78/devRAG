"""Actual index/query parity for traditional/simplified legal text."""

import pytest
from test.integration import test_pipeline_failures as base
from test.helpers.ingest import add_document, add_task, run_task, indexed
from test.helpers.uploads import sql
from test.helpers.doc_store_contract import search

_bound_database = base._bound_database
registry = base.registry
fake = base.fake
world = base.world
pytestmark = pytest.mark.integration


def test_real_laws_index_queries_share_article_and_keep_original_source(world, fake, repo_root):
    path = repo_root / "test/fixtures/phase6/laws-original.txt"
    doc = add_document(world, path.name, path.read_bytes())
    sql("UPDATE `document` SET `parser_id`=%s WHERE `id`=%s", ("laws", doc))
    result = run_task(world, add_task(doc))
    assert result.chunk_count == 3
    rows = sorted(indexed(world, doc_id=[doc]), key=lambda r: r["order_int"])
    assert "檔案保存期限為七十三年" in rows[0]["content_with_weight"]
    assert "档案" in rows[0]["content_ltks"]
    tokens = rows[0]["content_ltks"].split()
    offsets = rows[0]["content_token_offsets_int"]
    assert len(tokens) == len(offsets)
    assert rows[0]["content_with_weight"][slice(*offsets[tokens.index("档案")])] == "檔案"
    matches = []
    from common.doc_store.doc_store_base import MatchTextExpr
    from rag.nlp.tokenizer import tokenize

    for query in ["檔案保存期限", "档案保存期限"]:
        result = search(world.store(), world.index, [world.dataset.id], condition={"doc_id": [doc]}, matches=[MatchTextExpr(["content_ltks"], " ".join(tokenize(query)), 10)])
        matches.append([r["id"] for r in result.hits])
    assert matches[0] == matches[1] and rows[0]["id"] in matches[0]
