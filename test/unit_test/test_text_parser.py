"""TXT, Markdown, CSV and JSON parsing (plan 04-06, D-28, PARSE-13)."""

from __future__ import annotations

import os

import pytest

from rag.parsers import txt
from rag.parsers.errors import FileDamaged, FileTooLarge, NoReadableText
from rag.parsers.types import ParseLimits, ParseReport, SourceFile

pytestmark = pytest.mark.unit


def _run(path, suffix="txt", limits=None):
    source = SourceFile(path, suffix, path.stat().st_size)
    return [b.text for b in txt.parse(source, ParseReport(), limits=limits)]


def test_utf8_bom_is_dropped(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"\xef\xbb\xbfhello\n\nworld")
    assert _run(p) == ["hello", "world"]


def test_gbk_decodes_to_chinese(tmp_path):
    p = tmp_path / "a.txt"
    text = "这是一个用于测试字符集检测的中文段落，内容足够长以便检测。"
    p.write_bytes(text.encode("gbk"))
    assert _run(p) == [text]


def test_latin1_decodes(tmp_path):
    p = tmp_path / "a.txt"
    text = "Café crème brûlée et à la carte"
    p.write_bytes(text.encode("latin-1"))
    out = _run(p)
    assert len(out) == 1 and "Caf" in out[0]


def test_paragraphs_in_order(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# T\n\npara one\nline two\n\n\n\npara three\n", encoding="utf-8")
    assert _run(p, "md") == ["# T", "para one\nline two", "para three"]


def test_csv_and_json_are_raw_text(tmp_path):
    c = tmp_path / "a.csv"
    c.write_text("a,b\n1,2\n", encoding="utf-8")
    assert _run(c, "csv") == ["a,b\n1,2"]
    j = tmp_path / "a.json"
    j.write_text('{"k": 1}', encoding="utf-8")
    assert _run(j, "json") == ['{"k": 1}']


@pytest.mark.parametrize("data", [b"", b"  \n\n \t\n"])
def test_empty_or_blank_raises_no_readable_text(tmp_path, data):
    p = tmp_path / "secret-name.txt"
    p.write_bytes(data)
    with pytest.raises(NoReadableText) as info:
        _run(p)
    assert info.value.code == "no_readable_text"
    assert "secret-name" not in str(info.value) and str(tmp_path) not in str(info.value)


def test_too_large_raises(tmp_path):
    p = tmp_path / "big-file.txt"
    p.write_bytes(b"a" * 100)
    with pytest.raises(FileTooLarge) as info:
        _run(p, limits=ParseLimits(max_text_bytes=10))
    assert info.value.code == "file_too_large"
    assert "big-file" not in str(info.value)


def test_undecodable_binary_raises_file_damaged(tmp_path):
    p = tmp_path / "blob.txt"
    p.write_bytes(b"\x00\x01\x02\xff\xfe\x00\x00\x80" * 64 + os.urandom(0))
    with pytest.raises(FileDamaged) as info:
        _run(p)
    assert info.value.code == "file_damaged"
    assert "blob" not in str(info.value)
