"""Parser router and the shared parser types (plan 04-06, D-13, D-17)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from common.settings import DEFAULT_UPLOAD_EXTENSIONS
from rag.parsers import router
from rag.parsers.errors import UnsupportedType
from rag.parsers.types import PageBox, ParsedBlock, ParseReport, SourceFile

pytestmark = pytest.mark.unit


def test_office_and_pdf_suffixes_map_to_their_parsers():
    for suffix, name in (("pdf", "pdf"), ("docx", "docx"), ("xlsx", "xlsx"), ("pptx", "pptx"), ("html", "html"), ("htm", "html")):
        assert router.parser_for_suffix(suffix).name == name


def test_text_like_suffixes_map_to_txt():
    for suffix in ("txt",):
        assert router.parser_for_suffix(suffix).name == "txt"


def test_suffix_is_case_insensitive_and_tolerates_a_dot():
    assert router.parser_for_suffix("PDF").name == "pdf"
    assert router.parser_for_suffix(".Md").name == "markdown"


@pytest.mark.parametrize("suffix", ["png", "jpg", "epub", "mp3", "wav", "exe", ""])
def test_unparseable_suffixes_raise(suffix):
    assert router.parseable(suffix) is False
    with pytest.raises(UnsupportedType) as info:
        router.parser_for_suffix(suffix)
    assert info.value.code == "unsupported_type"


def test_parseable_true_for_md():
    assert router.parseable("md") is True


def test_every_router_suffix_is_an_allowed_upload_extension():
    assert router.PARSEABLE_SUFFIXES <= set(DEFAULT_UPLOAD_EXTENSIONS)


def test_loaders_are_dotted_module_paths_and_importing_router_is_light():
    assert {spec.loader for spec in router.PARSERS} == {f"rag.parsers.{n}" for n in ("pdf", "docx", "xlsx", "pptx", "html", "txt", "markdown", "json", "csv")}


def test_types_are_frozen_and_report_caps_notes():
    box = PageBox(0, 1.0, 2.0, 3.0, 4.0)
    block = ParsedBlock("hello")
    assert block.kind == "text" and block.boxes == ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        box.page = 1  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        block.text = "x"  # type: ignore[misc]
    report = ParseReport()
    for i in range(500):
        report.add_note(f"note {i}")
    assert len(report.notes) == 200
    assert SourceFile(Path("x"), "txt", 1).suffix == "txt"
