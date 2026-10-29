"""Table rows retain title, hierarchical headers, merged semantics and source evidence."""

import hashlib, json
import pytest
from rag.chunking import factory
from rag.parsers.types import ParsedBlock, SourceFile, ParseReport, PageBox
from rag.parsers.tables import Table, TableCell

pytestmark = pytest.mark.unit


def chunks(blocks, size=512):
    assert factory.available("table"), "Table implementation is missing"
    return list(factory.get_chunker("table")(blocks, factory.get_chunker_config("table", {"chunk_token_num": size})))


def test_typed_merged_headers_repeat_full_context_per_row_and_keep_boxes():
    grid = Table(
        4,
        3,
        (
            TableCell(0, 0, "Site", 2, 1, True),
            TableCell(0, 1, "Measurements", 1, 2, True),
            TableCell(1, 1, "Height metres", header=True),
            TableCell(1, 2, "Harvest apples", header=True),
            TableCell(2, 0, "Lighthouse"),
            TableCell(2, 1, "52"),
            TableCell(2, 2, ""),
            TableCell(3, 0, "Orchard"),
            TableCell(3, 1, "12"),
            TableCell(3, 2, "52"),
        ),
        caption="Site measurements",
    )
    box = PageBox(2, 10, 20, 300, 400)
    made = chunks([ParsedBlock(grid.plain_text(), "table", boxes=(box,), table=grid)])
    assert len(made) == 2
    assert all("Site measurements" in c.text and "Measurements" in c.text and "Height metres" in c.text and "Harvest apples" in c.text for c in made)
    assert "Lighthouse" in made[0].text and "Orchard" not in made[0].text
    assert "Orchard" in made[1].text and "Lighthouse" not in made[1].text
    assert all(c.positions == (box,) for c in made)
    assert all(c.tables for c in made)


def test_original_csv_and_xlsx_tables_have_exact_rows_and_source_lines(repo_root):
    from rag.parsers import csv, xlsx

    root = repo_root / "test/fixtures/phase6"
    gold = json.loads((root / "table-original-annotation.json").read_text())
    for suffix, module in [("csv", csv), ("xlsx", xlsx)]:
        p = root / f"table-original.{suffix}"
        assert hashlib.sha256(p.read_bytes()).hexdigest() == gold["sha256"][p.name]
        import inspect

        assert "structured_tables" in inspect.signature(module.parse).parameters, "Structured Table parser mode is missing"
        blocks = list(module.parse(SourceFile(p, suffix, p.stat().st_size), ParseReport(), structured_tables=True))
        made = chunks(blocks)
        assert len(made) == 2
        assert "Lighthouse" in made[0].text and "Orchard" not in made[0].text
        assert "Orchard" in made[1].text and "Lighthouse" not in made[1].text
        assert [list(c.source_lines[0]) for c in made] == gold["csv_lines" if suffix == "csv" else "xlsx_rows"]
        assert all(c.positions == () for c in made)


def test_wide_row_and_context_overflow_fail_without_splitting_values():
    from rag.chunking.errors import ChunkTooLong

    grid = Table(2, 2, (TableCell(0, 0, "Column A", header=True), TableCell(0, 1, "Column B", header=True), TableCell(1, 0, "very long value " * 100), TableCell(1, 1, "52")), caption="Source title")
    with pytest.raises(ChunkTooLong):
        chunks([ParsedBlock(grid.plain_text(), "table", table=grid)], 20)
    assert chunks([]) == []


def test_empty_cells_are_retained_and_plain_unstructured_text_refuses():
    from rag.parsers.errors import FileDamaged

    grid = Table(3, 2, (TableCell(0, 0, "Site", header=True), TableCell(0, 1, "Height", header=True), TableCell(1, 0, "Lighthouse"), TableCell(1, 1, ""), TableCell(2, 0, ""), TableCell(2, 1, "")))
    made = chunks([ParsedBlock(grid.plain_text(), "table", table=grid)])
    assert len(made) == 1 and "Height: " in made[0].text
    assert made[0].tables[0].cells[-1].text == ""
    with pytest.raises(FileDamaged):
        chunks([ParsedBlock("<table><table>malformed</table>")])


def test_pdf_surrounding_prose_does_not_become_a_table_row():
    grid = Table(2, 1, (TableCell(0, 0, "Height", header=True), TableCell(1, 0, "52")), caption="Measurements")
    made = chunks([ParsedBlock("Document heading"), ParsedBlock(grid.plain_text(), "table", table=grid), ParsedBlock("Footer prose")])
    assert len(made) == 1 and "Height: 52" in made[0].text
    assert "Footer" not in made[0].text and "Document heading" not in made[0].text


def test_table_xlsx_checks_actual_cell_budget_before_merge_materialization(repo_root):
    from rag.parsers import xlsx
    from rag.parsers.types import ParseLimits
    from rag.parsers.errors import FileTooLarge
    p=repo_root/'test/fixtures/phase6/table-original.xlsx'
    with pytest.raises(FileTooLarge):
        list(xlsx.parse(SourceFile(p,'xlsx',p.stat().st_size),ParseReport(),structured_tables=True,limits=ParseLimits(xlsx_max_cells=8)))


def test_csv_quoted_multiline_empty_and_duplicate_headers(tmp_path):
    from rag.parsers import csv
    from rag.parsers.errors import FileDamaged
    p=tmp_path/'quoted.csv';p.write_text('Site,Note\nLighthouse,"first\nsecond"\n')
    made=chunks(csv.parse(SourceFile(p,'csv',p.stat().st_size),ParseReport(),structured_tables=True))
    assert len(made)==1 and made[0].source_lines==((2,3),) and 'first\nsecond' in made[0].text
    p.write_text('Same,Same\na,b\n')
    with pytest.raises(FileDamaged):
        list(csv.parse(SourceFile(p,'csv',p.stat().st_size),ParseReport(),structured_tables=True))
