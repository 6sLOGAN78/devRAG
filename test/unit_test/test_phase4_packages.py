"""Phase 4 parsing-package pins and import smoke test (D-24, D-28)."""

import importlib
import json
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APPROVED = ["pypdfium2", "Pillow", "python-docx", "python-pptx", "openpyxl", "lxml", "beautifulsoup4"]
FORBIDDEN = ["pdfplumber", "chardet", "readability-lxml", "html-text", "infinity-sdk", "hanziconv", "defusedxml"]
FORBIDDEN_NPM = ["react-pdf-highlighter", "pdfjs-dist", "@tanstack/react-table"]
MODULES = ["pypdfium2", "PIL", "docx", "pptx", "openpyxl", "lxml.etree", "bs4", "charset_normalizer"]

pytestmark = pytest.mark.unit


def _direct_dependencies() -> list[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["dependencies"]


def _name(spec: str) -> str:
    return re.split(r"[<>=!~\[ ;]", spec, maxsplit=1)[0].lower().replace("_", "-")


@pytest.mark.parametrize("module", MODULES)
def test_module_imports_under_warnings_as_errors(module: str) -> None:
    importlib.import_module(module)


@pytest.mark.parametrize("package", APPROVED)
def test_approved_package_is_pinned_exactly(package: str) -> None:
    specs = {_name(s): s for s in _direct_dependencies()}
    assert package.lower() in specs
    assert "==" in specs[package.lower()]


def test_charset_normalizer_is_direct_and_chardet_is_not() -> None:
    names = {_name(s) for s in _direct_dependencies()}
    assert "charset-normalizer" in names
    assert "chardet" not in names


def test_soupsieve_is_held_below_three() -> None:
    specs = {_name(s): s for s in _direct_dependencies()}
    assert "<3" in specs["soupsieve"].replace(" ", "")


@pytest.mark.parametrize("package", FORBIDDEN)
def test_forbidden_package_is_absent(package: str) -> None:
    assert package not in {_name(s) for s in _direct_dependencies()}


def test_no_forbidden_npm_package() -> None:
    pkg = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    declared = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    for name in FORBIDDEN_NPM:
        assert name not in declared
