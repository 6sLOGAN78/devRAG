"""Real row indexing for CSV and merged XLSX with exact header context."""

import pytest
from test.integration import test_pipeline_failures as base
from test.helpers.ingest import add_document, add_task, run_task, indexed, begin_run
from test.helpers.uploads import sql

_bound_database = base._bound_database
registry = base.registry
fake = base.fake
world = base.world
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("suffix", ["csv", "xlsx"])
def test_table_rows_keep_header_context_and_source_provenance(world, fake, repo_root, suffix):
    p = repo_root / f"test/fixtures/phase6/table-original.{suffix}"
    doc = add_document(world, p.name, p.read_bytes())
    sql("UPDATE `document` SET `parser_id`=%s WHERE `id`=%s", ("table", doc))
    result = run_task(world, add_task(doc))
    assert result.chunk_count == 2
    rows = sorted(indexed(world, doc_id=[doc]), key=lambda r: r["order_int"])
    if suffix == "csv":
        assert "table-original" in rows[0]["content_with_weight"]
    assert "Lighthouse" in rows[0]["content_with_weight"] and "Orchard" not in rows[0]["content_with_weight"]
    assert "Height metres: 52" in rows[0]["content_with_weight"]
    assert "Harvest apples: 52" in rows[1]["content_with_weight"]
    assert all(r["position_int"] == [] and "table_features_with_weight" in r for r in rows)
    assert [r["source_lines_int"] for r in rows] == ([[[2, 2]], [[3, 3]]] if suffix == "csv" else [[[3, 3]], [[4, 4]]])


def test_actual_pdf_row_chunks_keep_native_header_caption_crop_and_geometry(world, fake, repo_root):
    p = repo_root / "test/fixtures/phase6/table-spanned-original.pdf"
    doc = add_document(world, p.name, p.read_bytes())
    sql("UPDATE `document` SET `parser_id`=%s WHERE `id`=%s", ("table", doc))
    from dataclasses import replace
    from common.settings import DeepDocSettings
    from test.conftest import stack_env
    token = stack_env().get("DEEPDOC_API_TOKEN")
    assert token
    settings = replace(world.settings,deepdoc=DeepDocSettings(url="http://127.0.0.1:9390",api_token=token))
    task = add_task(doc)
    begin_run(doc)
    result = run_task(world, task, deps=world.deps(settings=settings))
    rows = sorted(indexed(world, doc_id=[doc]), key=lambda r: r["order_int"])
    assert result.chunk_count == 6
    assert all("ORCHARD MEASUREMENTS" in r["content_with_weight"] and "Orchard field measurements" in r["content_with_weight"] for r in rows)
    assert any("9100" in r["content_with_weight"] for r in rows)
    assert all(r["position_int"] and r["table_features_with_weight"] for r in rows)
