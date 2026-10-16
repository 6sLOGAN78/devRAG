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
