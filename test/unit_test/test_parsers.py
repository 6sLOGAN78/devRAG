"""DOCX, XLSX, PPTX and HTML parsers (plan 04-09, PARSE-09..12, D-27)."""

from __future__ import annotations

import pytest

from rag.parsers import docx as docx_parser
from rag.parsers import html as html_parser
from rag.parsers import pptx as pptx_parser
from rag.parsers import xlsx as xlsx_parser
from rag.parsers.errors import FileDamaged, NoReadableText
from rag.parsers.types import ParseLimits, ParseReport, SourceFile
from test.helpers import office_files as of

pytestmark = pytest.mark.unit


def _src(tmp_path, data: bytes, suffix: str) -> SourceFile:
    path = tmp_path / f"f.{suffix}"
    path.write_bytes(data)
    return SourceFile(path=path, suffix=suffix, size=len(data))


def _run(module, source, limits=None):
    report = ParseReport()
    return list(module.parse(source, report, limits=limits)), report


def test_docx_order_headings_tables_images(tmp_path):
    data = of.make_docx(["P1", "P2"], headings=["Intro"], table=[["a", "<b>"], ["c", "d"]], image=True)
    blocks, report = _run(docx_parser, _src(tmp_path, data, "docx"))
    kinds = {b.text: b.kind for b in blocks}
    assert kinds["Intro"] == "heading"
    texts = [b.text for b in blocks]
    assert texts.index("Intro") < texts.index("P1") < texts.index("P2")
    table = next(b for b in blocks if b.kind == "table")
    assert "<table>" in table.text and "<td>" in table.text and "&lt;b&gt;" in table.text and "<b>" not in table.text
    assert report.images_skipped == 1
    assert any("1" in n for n in report.notes)


def test_xlsx_groups_header_and_cap(tmp_path):
    rows = [["h1", "h2"]] + [[i, i * 2] for i in range(60)]
    data = of.make_xlsx({"Alpha": rows, "Beta": rows})
    blocks, _ = _run(xlsx_parser, _src(tmp_path, data, "xlsx"))
    alpha = [b for b in blocks if b.text.startswith("Alpha")]
    assert len(alpha) == 3 and len([b for b in blocks if b.text.startswith("Beta")]) == 3
    assert all("h1" in b.text for b in alpha)
    blocks, report = _run(xlsx_parser, _src(tmp_path, data, "xlsx"), ParseLimits(xlsx_max_cells=30))
    assert blocks and any("stopped" in n for n in report.notes)


def test_xlsx_cached_formula_values(tmp_path):
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.append(["x"])
    wb.active.append(["=1+1"])
    out = io.BytesIO()
    wb.save(out)
    blocks, _ = _run(xlsx_parser, _src(tmp_path, out.getvalue(), "xlsx"))
    assert all("=1+1" not in b.text for b in blocks)


def test_pptx_slides(tmp_path):
    data = of.make_pptx(
        [
            {"title": "Alpha", "body": "first body", "notes": "speaker words", "image": True},
            {"title": "Beta", "body": "second", "table": [["c1", "c2"]]},
        ]
    )
    blocks, report = _run(pptx_parser, _src(tmp_path, data, "pptx"))
    assert [b.kind for b in blocks] == ["slide", "slide"]
    first = blocks[0].text
    assert first.index("Alpha") < first.index("first body") and "speaker words" in first
    assert "c1" in blocks[1].text and "c2" in blocks[1].text
    assert report.images_skipped == 1


def test_html_clean_text(tmp_path):
    markup = (
        "<html><head><title>T</title></head><body><script>alert(1)</script><style>p{}</style><!-- c -->"
        "<noscript>nojs</noscript><template><p>tpl</p></template><h1>Title</h1><p>Body &amp; more</p></body></html>"
    )
    blocks, _ = _run(html_parser, _src(tmp_path, of.make_html(markup), "html"))
    assert blocks[0].text == "Title" and blocks[0].kind == "heading"
    assert any(b.text == "Body & more" for b in blocks)
    joined = " ".join(b.text for b in blocks)
    for bad in ("alert", "p{}", "<", "-->", "nojs", "tpl"):
        assert bad not in joined


def test_html_latin1_and_empty(tmp_path):
    blocks, _ = _run(html_parser, _src(tmp_path, of.make_html("<p>café crème brûlée</p>", "latin-1"), "html"))
    assert "café" in blocks[0].text
    with pytest.raises(NoReadableText):
        _run(html_parser, _src(tmp_path, b"<script>x</script>", "html"))


@pytest.mark.parametrize(
    ("module", "suffix"), [(docx_parser, "docx"), (xlsx_parser, "xlsx"), (pptx_parser, "pptx")]
)
def test_damaged_files(tmp_path, module, suffix):
    source = _src(tmp_path, of.poison_docx(), suffix)
    with pytest.raises(FileDamaged) as info:
        _run(module, source)
    assert str(tmp_path) not in str(info.value)


def test_truncated_xlsx_and_entity_docx(tmp_path):
    data = of.make_xlsx({"S": [["a"]]})
    with pytest.raises(FileDamaged):
        _run(xlsx_parser, _src(tmp_path, data[: len(data) // 2], "xlsx"))
    with pytest.raises(FileDamaged) as info:
        _run(docx_parser, _src(tmp_path, of.make_entity_docx(), "docx"))
    assert str(tmp_path) not in str(info.value)
