"""Archive and XML guard for OOXML files (plan 04-09, R-161, T-04-09-01/02)."""

from __future__ import annotations

import zipfile

import pytest

from rag.parsers.errors import ArchiveLimitsExceeded, FileDamaged
from rag.parsers.limits import check_ooxml_limits
from test.helpers import office_files

pytestmark = pytest.mark.unit


def _write(tmp_path, data: bytes, name: str = "f.docx"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_normal_docx_passes(tmp_path):
    assert check_ooxml_limits(_write(tmp_path, office_files.make_docx(["hello"]))) is None


def test_member_count(tmp_path):
    path = tmp_path / "m.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for i in range(3):
            zf.writestr(f"a{i}.txt", "x")
    with pytest.raises(ArchiveLimitsExceeded):
        check_ooxml_limits(path, max_members=2)


def test_member_size_and_total(tmp_path):
    path = tmp_path / "m.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("big.bin", b"x" * 5000)
    with pytest.raises(ArchiveLimitsExceeded):
        check_ooxml_limits(path, max_member=1000)
    with pytest.raises(ArchiveLimitsExceeded):
        check_ooxml_limits(path, max_total=1000)


def test_ratio_bomb(tmp_path):
    path = office_files.make_zip_bomb(tmp_path / "bomb.docx", 3 * 2**20)
    assert path.stat().st_size < 5 * 2**20
    with pytest.raises(ArchiveLimitsExceeded):
        check_ooxml_limits(path)


def test_not_a_zip_and_truncated(tmp_path):
    with pytest.raises(FileDamaged):
        check_ooxml_limits(_write(tmp_path, office_files.poison_docx()))
    data = office_files.make_docx(["hello"])
    with pytest.raises(FileDamaged):
        check_ooxml_limits(_write(tmp_path, data[: len(data) // 2], "t.docx"))


def test_entity_declaration_refused_without_leaking(tmp_path):
    path = _write(tmp_path, office_files.make_entity_docx())
    with pytest.raises(FileDamaged) as info:
        check_ooxml_limits(path)
    assert "not allowed" in str(info.value)
    assert str(tmp_path) not in str(info.value)
    assert "document.xml" not in str(info.value)


def test_doctype_case_insensitive(tmp_path):
    data = office_files._rezip(office_files.make_docx(["x"]), {"word/document.xml": b"<!doctype x><a/>"})
    with pytest.raises(FileDamaged):
        check_ooxml_limits(_write(tmp_path, data))


# --- security hardening (post-review): encoding, scan window and extension bypasses ----------------------------------------

_HOSTILE = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/hostname">]><r>&e;</r>'


def _with_part(name: str, payload: bytes) -> bytes:
    return office_files._rezip(office_files.make_docx(["x"]), {name: payload})


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be"])
def test_utf16_doctype_refused(tmp_path, encoding):
    payload = _HOSTILE.encode(encoding)
    if encoding != "utf-16":
        payload = b"\xff\xfe" + payload if encoding == "utf-16-le" else payload
    with pytest.raises(FileDamaged):
        check_ooxml_limits(_write(tmp_path, _with_part("word/document.xml", payload)))


def test_non_utf8_declared_encoding_refused(tmp_path):
    payload = '<?xml version="1.0" encoding="UTF-32"?><r/>'.encode("utf-8")
    with pytest.raises(FileDamaged):
        check_ooxml_limits(_write(tmp_path, _with_part("word/document.xml", payload)))


def test_doctype_after_scan_window_refused(tmp_path):
    pad = b"<!-- " + b"a" * (8 * 2**20 + 1024) + b" -->"
    payload = b'<?xml version="1.0"?><r>' + pad + _HOSTILE.encode().split(b"?>", 1)[1] + b"</r>"
    with pytest.raises(FileDamaged):
        check_ooxml_limits(_write(tmp_path, _with_part("word/document.xml", payload)))


def test_token_straddling_chunk_boundary_refused(tmp_path):
    for offset in range(-12, 12):
        filler = b"a" * (1024 * 1024 + offset)
        payload = b"<r><!--" + filler + b"--><!DOCTYPE x></r>"
        with pytest.raises(FileDamaged):
            check_ooxml_limits(_write(tmp_path, _with_part("word/document.xml", payload)))


@pytest.mark.parametrize("name", ["word/evil.bin", "word/evil", "customXml/item1.data"])
def test_doctype_in_member_without_xml_suffix_refused(tmp_path, name):
    with pytest.raises(FileDamaged):
        check_ooxml_limits(_write(tmp_path, _with_part(name, _HOSTILE.encode())))


def test_binary_member_with_doctype_text_is_not_scanned(tmp_path):
    payload = b"\x89PNG\r\n" + b"<!DOCTYPE inside a png chunk"
    assert check_ooxml_limits(_write(tmp_path, _with_part("word/media/image1.png", payload))) is None


def test_other_normal_office_files_pass(tmp_path):
    assert check_ooxml_limits(_write(tmp_path, office_files.make_xlsx({"S": [[1, "a"]]}), "a.xlsx")) is None
    assert check_ooxml_limits(_write(tmp_path, office_files.make_pptx([{"title": "t"}]), "a.pptx")) is None
