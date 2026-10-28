"""Structural original Markdown and Manual boundaries; no execution or external fetch."""

import pytest
from rag.chunking import factory
from rag.parsers.router import parser_for_suffix
from rag.parsers.types import SourceFile, ParseReport, ParseLimits

pytestmark = pytest.mark.unit


def parse(path, *, limits=None):
    spec = parser_for_suffix("md")
    assert spec.name == "markdown", "Markdown is still routed as plain TXT"
    report = ParseReport()
    return list(spec.load().parse(SourceFile(path, "md", path.stat().st_size), report, limits=limits)), report


def test_original_markdown_preserves_headings_full_fences_and_parameter_table(repo_root):
    path = repo_root / "test/fixtures/phase6/manual-original.md"
    blocks, _ = parse(path)
    assert [b.heading_level for b in blocks if b.kind == "heading"] == [1, 2, 2]
    code = [b for b in blocks if b.kind == "code"]
    assert len(code) == 2
    expected = path.read_text().split("````python\n", 1)[1].split("\n````", 1)[0]
    assert code[0].text == "````python\n" + expected + "\n````\n"
    assert "# This is code" in code[0].text
    assert len([b for b in blocks if b.kind == "table"]) == 1
    assert "| harvest | 9100 | kg |" in next(b.text for b in blocks if b.kind == "table")
    assert all(b.line_range[0] <= b.line_range[1] for b in blocks)
    assert [b.line_range[0] for b in blocks] == sorted(b.line_range[0] for b in blocks)
    assert all(b.boxes == () for b in blocks), "Markdown must not invent page coordinates"


def test_manual_keeps_code_table_diagram_and_subsection_together(repo_root):
    assert factory.available("manual"), "Manual implementation is missing"
    blocks, _ = parse(repo_root / "test/fixtures/phase6/manual-original.md")
    chunks = list(factory.get_chunker("manual")(blocks, factory.get_chunker_config("manual", {"chunk_token_num": 512, "delimiter": ".*+?"})))
    assert len(chunks) == 2
    assert chunks[0].text.startswith("# Orchard controller\n")
    assert "LIGHTHOUSE FACT: tower height 52 metres." in chunks[0].text
    assert "ORCHARD FACT: harvest 9100 kilograms." in chunks[0].text
    assert "| harvest | 9100 | kg |" in chunks[0].text
    assert "![Orchard controller wiring 52](https://example.invalid/diagram.png)" in chunks[0].text
    assert "CALIBRATION FACT" not in chunks[0].text
    assert chunks[1].text.startswith("# Orchard controller\n")
    assert "Calibration\n-----------" in chunks[1].text and "CALIBRATION FACT: offset 73 units." in chunks[1].text
    for block in blocks:
        if block.kind == "code":
            assert any(block.text in chunk.text for chunk in chunks)
    assert all(chunk.source_lines for chunk in chunks)


def test_unclosed_fence_stays_literal_through_end_of_file(tmp_path):
    p = tmp_path / "unclosed.md"
    p.write_text("# Heading\n\n```python\n# not a heading\nprint(52)\n")
    blocks, report = parse(p)
    assert len(blocks) == 2 and blocks[1].kind == "code"
    assert blocks[1].text == "```python\n# not a heading\nprint(52)\n"
    assert report.notes == ["A Markdown code fence is not closed."]


def test_markdown_does_not_execute_or_fetch_any_link(repo_root, monkeypatch):
    import socket, subprocess

    def forbidden(*a, **k):
        raise AssertionError("Markdown attempted execution or a network request")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    blocks, _ = parse(repo_root / "test/fixtures/phase6/manual-original.md")
    assert any("<script>window.manualExecuted" in b.text for b in blocks)
    assert len([b for b in blocks if b.kind == "image"]) == 2
    assert all(not b.assets for b in blocks)


@pytest.mark.parametrize("body,limit", [("x" * 262145, None), ("# Heading\n" + "x" * 50, 10)])
def test_markdown_limits_refuse_before_unbounded_line_or_text(tmp_path, body, limit):
    from rag.parsers.errors import FileTooLarge

    p = tmp_path / "large.md"
    p.write_text(body)
    with pytest.raises(FileTooLarge):
        parse(p, limits=ParseLimits(max_text_bytes=limit) if limit else None)


def test_manual_refuses_an_oversize_atomic_code_group_without_splitting(tmp_path):
    assert factory.available("manual"), "Manual implementation is missing"
    from rag.chunking.errors import ChunkTooLong

    p = tmp_path / "large-code.md"
    p.write_text("# Code\n\n```\n" + "word " * 9000 + "\n```\n")
    blocks, _ = parse(p)
    with pytest.raises(ChunkTooLong):
        list(factory.get_chunker("manual")(blocks, factory.get_chunker_config("manual", {})))


def test_indented_fence_text_does_not_close_the_code_or_hide_next_heading(tmp_path):
    p = tmp_path / "indent.md"
    p.write_text("# Setup\n\n````python\n    ````\nprint(52)\n````\n\n## Next\n\nNEXT FACT 9100\n")
    blocks, _ = parse(p)
    code = next(b for b in blocks if b.kind == "code")
    assert code.text == "````python\n    ````\nprint(52)\n````\n"
    assert any(b.kind == "heading" and "Next" in b.text for b in blocks)


def test_table_does_not_swallow_a_following_heading_containing_a_pipe(tmp_path):
    p = tmp_path / "table.md"
    p.write_text("# First\n\n| P | V |\n|---|---|\n| height | 52 |\n## Next | Section\n\nVALUE 9100\n")
    blocks, _ = parse(p)
    assert next(b.text for b in blocks if b.kind == "table").endswith("| height | 52 |\n")
    assert any(b.kind == "heading" and b.text == "## Next | Section\n" for b in blocks)


def test_manual_retains_geometry_table_image_and_line_evidence():
    from rag.parsers.types import ParsedBlock, PageBox
    from rag.parsers.tables import Table, TableCell

    table = Table(1, 1, (TableCell(0, 0, "52"),), asset_id="a" * 32)
    box = PageBox(2, 10, 20, 30, 40)
    blocks = [
        ParsedBlock("## Setup\n", "heading", heading_level=2, line_range=(1, 1)),
        ParsedBlock("52", "table", boxes=(box,), page_sizes={2: (600, 800)}, table=table, image_ids=("a" * 32,), line_range=(3, 5)),
    ]
    (chunk,) = factory.get_chunker("manual")(blocks, factory.get_chunker_config("manual", {}))
    assert chunk.positions == (box,) and chunk.page_sizes == {2: (600, 800)}
    assert chunk.tables == (table,) and chunk.image_ids == ("a" * 32,)
    assert chunk.source_lines == ((1, 1), (3, 5))


def test_manual_actual_embedding_context_guard_precedes_encode(monkeypatch):
    from types import SimpleNamespace
    from contextlib import nullcontext
    from rag.svr.embedding import EmbedRunner
    from rag.svr.failure import TaskFailure

    calls = []
    bundle = SimpleNamespace(token_limit=3, encode=lambda text: (calls.append(text) or [[1.0]], 0))
    runner = EmbedRunner(SimpleNamespace(), SimpleNamespace(embed_limiter=nullcontext()))
    monkeypatch.setattr(runner, "_bundle", lambda *a: bundle)
    monkeypatch.setattr("rag.svr.embedding.release_database_connection", lambda: None)
    with pytest.raises(TaskFailure) as failure:
        runner._encode_blocking(["word " * 10], SimpleNamespace(parser_id="manual"), 1)
    assert failure.value.code == "chunk_too_long" and calls == []


def test_long_prose_chunks_repeat_the_complete_heading_path(tmp_path):
    p = tmp_path / "prose.md"
    p.write_text("# Orchard\n\n## Calibration\n\n" + "measured value " * 150 + "FINAL FACT 73\n")
    blocks, _ = parse(p)
    chunks = list(factory.get_chunker("manual")(blocks, factory.get_chunker_config("manual", {"chunk_token_num": 60})))
    assert len(chunks) > 2
    assert all("# Orchard\n" in c.text and "## Calibration\n" in c.text for c in chunks)
    assert all(c.token_num <= 60 for c in chunks)
    assert "FINAL FACT 73" in chunks[-1].text
