"""Frozen structured table semantics: exact spans/empty cells, safe text and geometry."""

import importlib

import pytest

from rag.parsers.types import ParsedBlock

pytestmark = pytest.mark.unit


def tables():
    assert importlib.util.find_spec("deepdoc.tables") is not None, "structured table reconstruction is missing"
    return importlib.import_module("deepdoc.tables")


def test_parsed_blocks_and_chunks_have_backward_compatible_table_metadata():
    from rag.chunking.types import Chunk

    assert "table" in ParsedBlock.__dataclass_fields__, "parsed cells cannot reach chunking"
    assert "tables" in Chunk.__dataclass_fields__, "structured cells cannot survive indexing"
    assert ParsedBlock("old source").table is None
    assert Chunk("old source", (), {}, 1, 0).tables == ()


def test_exact_merged_header_empty_cell_and_html_escaping():
    module = tables()
    cells = [
        module.TableCell(0, 0, "ORCHARD MEASUREMENTS", colspan=3, header=True),
        module.TableCell(1, 0, "Metric", header=True),
        module.TableCell(1, 1, "Recorded", header=True),
        module.TableCell(1, 2, "Unit", header=True),
        module.TableCell(2, 0, "Harvest"),
        module.TableCell(2, 1, "9100"),
        module.TableCell(2, 2, "kg"),
        module.TableCell(3, 0, "<b>Literal</b>"),
        module.TableCell(3, 1, "73"),
        module.TableCell(3, 2, ""),
    ]
    table = module.Table(4, 3, tuple(cells))
    expected = '<table>\n<tr><th colspan="3">ORCHARD MEASUREMENTS</th></tr>\n<tr><th>Metric</th><th>Recorded</th><th>Unit</th></tr>\n<tr><td>Harvest</td><td>9100</td><td>kg</td></tr>\n<tr><td>&lt;b&gt;Literal&lt;/b&gt;</td><td>73</td><td></td></tr>\n</table>'
    assert table.html() == expected
    assert table.cells[-1].text == ""


def test_overlapping_or_out_of_bounds_spans_are_refused():
    m = tables()
    for cells in [(m.TableCell(0, 0, "a", colspan=2), m.TableCell(0, 1, "overlap")), (m.TableCell(0, 0, "outside", rowspan=3),)]:
        with pytest.raises(ValueError):
            m.Table(2, 2, cells)


def test_table_fixture_hash_and_annotated_empty_cell_are_frozen(repo_root):
    import hashlib
    import json

    root = repo_root / "test/fixtures/phase6"
    expected = json.loads((root / "table-spanned-original.json").read_text())
    assert hashlib.sha256((root / "table-spanned-original.pdf").read_bytes()).hexdigest() == expected["sha256"]
    assert expected["merged_header"]["colspan"] == 3 and expected["body_rows_by_page"]["1"][-1][-1] == ""


def test_source_rulings_recover_a_merged_header_without_changing_model_scores():
    m = tables()
    assert hasattr(m, "reconstruct"), "model/text/ruling cell association is missing"
    regions = [
        m.StructureRegion(1, 0.8, (0, 0, 100, 150)),
        m.StructureRegion(1, 0.8, (100, 0, 200, 150)),
        m.StructureRegion(2, 0.8, (0, 50, 200, 100)),
        m.StructureRegion(2, 0.8, (0, 100, 200, 150)),
        m.StructureRegion(3, 0.8, (0, 50, 200, 100)),
    ]
    grid = m.TableGrid((0, 50, 100, 150), (0, 100, 200), ((False,), (True,), (True,)), ((True, True), (True, True)))
    tokens = [
        m.TextToken("Report", (40, 10, 160, 30)),
        m.TextToken("Item", (10, 60, 40, 80)),
        m.TextToken("Value", (110, 60, 150, 80)),
        m.TextToken("Harvest", (10, 110, 60, 130)),
        m.TextToken("9100", (110, 110, 150, 130)),
    ]
    made = m.reconstruct(regions, tokens, grid=grid)
    assert (made.rows, made.columns) == (3, 2)
    assert made.cells[0].text == "Report" and made.cells[0].colspan == 2
    assert made.cells[-1].text == "9100"


def test_table_metadata_survives_general_chunking_and_indexing_without_crop_bytes():
    import json

    from rag.chunking.naive import NaiveConfig, chunk
    from rag.svr.chunk_doc import build_row

    m = tables()
    table = m.Table(1, 1, (m.TableCell(0, 0, "9100"),), asset_id="a" * 32, asset_sha256="b" * 64)
    blocks = [ParsedBlock("9100", kind="table", table=table)]
    chunks = list(chunk(blocks, NaiveConfig()))
    assert chunks[0].tables == (table,), "table structures were discarded by General chunking"
    row = build_row(chunks[0], index=0, doc_id="c" * 32, kb_id="d" * 32, doc_name="table.pdf", task_id="e" * 32, from_page=0, to_page=1, vector=[1.0, 0.0], enabled=True)
    assert "table_features_with_weight" in row, "owned table metadata never reaches the index"
    raw = json.loads(row["table_features_with_weight"])
    assert raw[0]["asset_id"] == "a" * 32 and raw[0]["cells"][0]["text"] == "9100"
    assert "asset_sha256" not in row["table_features_with_weight"] and "content_base64" not in str(row)


def test_public_table_metadata_refuses_internal_paths_and_nonfinite_spans():
    import json
    from rag.parsers.table_features import TABLE_FIELD, tables_of

    m = tables()
    valid = m.Table(1, 1, (m.TableCell(0, 0, "<img src=x onerror=alert(1)>"),), asset_id="a" * 32).to_dto()
    assert tables_of({TABLE_FIELD: json.dumps([valid])}) == [valid]
    for change in ["path", "span", "internal"]:
        bad = json.loads(json.dumps(valid))
        if change == "path":
            bad["asset_id"] = "../../private.png"
        if change == "span":
            bad["cells"][0]["rowspan"] = float("inf")
        if change == "internal":
            bad["object_key"] = "private/key"
        assert tables_of({TABLE_FIELD: json.dumps([bad])}) == []


def test_saved_table_references_follow_existing_dataset_redaction(monkeypatch):
    from api.db.services import conversation_redaction as redaction

    m = tables()
    table = m.Table(1, 1, (m.TableCell(0, 0, "9100"),), asset_id="a" * 32).to_dto()
    message = {"role": "assistant", "content": "saved answer", "reference": {"chunks": [{"index": 0, "doc_id": "doc", "dataset_id": "dataset", "tables": [table]}]}}
    monkeypatch.setattr(redaction, "live_datasets", lambda ids: {"dataset": object()})
    monkeypatch.setattr(redaction, "openable", lambda *args: True)
    assert redaction.redact_messages([message], "tenant", "user")[0]["reference"]["chunks"][0]["tables"] == [table]
    monkeypatch.setattr(redaction, "openable", lambda *args: False)
    assert redaction.redact_messages([message], "tenant", "user")[0]["reference"]["chunks"] == [{"index": 0, "unavailable": True}]


@pytest.mark.parametrize("change", ["valid", "dimensions", "page", "digest", "spans"])
def test_remote_table_crop_requires_matching_owned_descriptor_geometry(repo_root, tmp_path, change):
    import httpx
    from common.settings import DeepDocSettings
    from rag.parsers.assets import ParsedAsset, encode_asset
    from rag.parsers.deepdoc_client import DeepDocClient, NativeUnavailable
    from rag.parsers.types import ParseReport, SourceFile

    m = tables()
    asset = ParsedAsset.from_png((repo_root / "test/fixtures/phase6/ocr-planted.png").read_bytes(), width=1400, height=400, page=1, kind="table")
    table = m.Table(1, 1, (m.TableCell(0, 0, "9100"),), asset_sha256=asset.sha256).to_wire()
    image = encode_asset(asset)
    if change == "dimensions":
        image["width"] = 1405
    if change == "page":
        image["page"] = 2
    if change == "digest":
        table["asset_sha256"] = "0" * 64
    if change == "spans":
        table["cells"][0]["rowspan"] = 2
    payload = {
        "schema_version": 1,
        "report": {"pages_total": 1, "pages_without_text": 0},
        "blocks": [{"text": "9100", "kind": "table", "boxes": [{"page": 1, "x0": 0, "top": 0, "x1": 1400 / 3, "bottom": 400 / 3}], "page_sizes": {"1": [600, 400]}, "table": table, "assets": [image]}],
    }
    client = DeepDocClient(DeepDocSettings(url="http://native.test", api_token="a" * 32), transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))
    path = tmp_path / "remote.pdf"
    path.write_bytes(b"remote native bytes only")
    if change == "valid":
        assert client.parse(SourceFile(path, "pdf", path.stat().st_size), ParseReport(), page_range=(0, 1), limits=None)[0].table.rows == 1
    else:
        with pytest.raises(NativeUnavailable):
            client.parse(SourceFile(path, "pdf", path.stat().st_size), ParseReport(), page_range=(0, 1), limits=None)


def test_native_word_rectangles_preserve_caption_punctuation(repo_root):
    from deepdoc import pdf

    document = pdf._open(repo_root / "test/fixtures/phase6/table-spanned-original.pdf")
    try:
        page = document[0]
        try:
            words = pdf.page_words(page)
        finally:
            page.close()
    finally:
        document.close()
    caption = [word.text for word in words if word.box[3] < 80]
    assert " ".join(caption) == "Table 1. Orchard field measurements"


def test_visible_whitespace_counts_empty_columns_instead_of_endpoint_distance():
    from deepdoc.ocr import word_spans

    # Ink at40 and50 encloses9 white columns: below0.35*28, so no word break.
    assert word_spans(list(range(7, 41)) + list(range(50, 90)), 28) == [(7, 90)]
    # Ten actual white columns exceed the same unchanged threshold.
    assert word_spans(list(range(7, 41)) + list(range(51, 90)), 28) == [(7, 41), (51, 90)]


def test_model_rowspan_and_projected_header_keep_all_cells():
    m = tables()
    regions = [
        m.StructureRegion(1, 0.8, (0, 0, 100, 100)),
        m.StructureRegion(1, 0.8, (100, 0, 200, 100)),
        m.StructureRegion(2, 0.8, (0, 0, 200, 50)),
        m.StructureRegion(2, 0.8, (0, 50, 200, 100)),
        m.StructureRegion(4, 0.8, (0, 0, 100, 100)),
        m.StructureRegion(5, 0.8, (0, 0, 100, 100)),
    ]
    table = m.reconstruct(regions, [m.TextToken("Harvest", (10, 20, 80, 30)), m.TextToken("9100", (110, 20, 160, 30)), m.TextToken("kg", (110, 70, 130, 80))])
    assert (table.rows, table.columns) == (2, 2)
    assert table.cells[0].rowspan == 2 and table.cells[0].colspan == 1 and table.cells[0].header is True
    assert table.html() == '<table>\n<tr><th rowspan="2">Harvest</th><td>9100</td></tr>\n<tr><td>kg</td></tr>\n</table>'


def test_empty_last_cell_does_not_absorb_the_next_source_caption():
    from rag.chunking.naive import NaiveConfig, chunk

    m = tables()
    table = m.Table(1, 2, (m.TableCell(0, 0, "73"), m.TableCell(0, 1, "")))
    made = list(chunk([ParsedBlock(table.plain_text(), kind="table", table=table), ParsedBlock("Table 2. Orchard field measurements")], NaiveConfig()))
    assert "\nTable 2." in made[0].text, "next source caption became apparent empty-cell text"
    assert "| Table 2." not in made[0].text
