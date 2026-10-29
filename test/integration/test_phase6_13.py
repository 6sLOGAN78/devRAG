"""Actual PPTX worker/index preserves typed slide identities and safe tables."""

import pytest
from test.integration import test_pipeline_failures as base
from test.helpers.ingest import add_document, add_task, run_task, indexed
from test.helpers.uploads import sql

_bound_database = base._bound_database
registry = base.registry
fake = base.fake
world = base.world
pytestmark = pytest.mark.integration


def test_real_presentation_has_original_slide_numbers_stable_ids_and_notes(world, fake, repo_root):
    p = repo_root / "test/fixtures/phase6/presentation-original.pptx"
    doc = add_document(world, p.name, p.read_bytes())
    sql("UPDATE `document` SET `parser_id`=%s, `parser_config`=%s WHERE `id`=%s", ("presentation", '{"chunk_token_num":64}', doc))
    task = add_task(doc)
    result = run_task(world, task)
    rows = sorted(indexed(world, doc_id=[doc]), key=lambda r: r["order_int"])
    assert result.chunk_count == len(rows) and len(rows) > 4
    assert sorted({r["slide_number_int"] for r in rows}) == [1, 3, 4]
    assert all(r["position_int"] == [] for r in rows)
    assert any("73 units" in r["content_with_weight"] for r in rows if r["slide_number_int"] == 1)
    assert any("O9100" in r["content_with_weight"] for r in rows if r["slide_number_int"] == 4)
    assert all("ORCHARD" not in r["content_with_weight"] for r in rows if r["slide_number_int"] == 1)
    from api.db.services.chunk_view import chunk_view_fields

    assert any(chunk_view_fields(r).get("tables") for r in rows if r["slide_number_int"] == 1)
    from test.integration.test_chunk_service import listing
    page = listing(world, doc)
    assert sorted({c["slide"]["number"] for c in page["items"]}) == [1,3,4]
    before = [(r["id"], r["content_with_weight"]) for r in rows]
    run_task(world, task)
    assert [(r["id"], r["content_with_weight"]) for r in sorted(indexed(world, doc_id=[doc]), key=lambda r: r["order_int"])] == before
