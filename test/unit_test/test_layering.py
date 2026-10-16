"""Layering (API-06): handlers -> services -> models/adapters, enforced on the import graph."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _violations(directory: str, forbidden: tuple[str, ...]) -> list[str]:
    found = []
    for path in sorted((ROOT / directory).rglob("*.py")):
        for name in _imports(path):
            if any(name == f or name.startswith(f + ".") for f in forbidden):
                found.append(f"{path.relative_to(ROOT)} imports {name}")
    return found


def test_apps_do_not_touch_models_database_peewee_or_probes():
    assert _violations("api/apps", ("api.db.models", "api.db.database", "peewee", "common.health")) == []


def test_services_do_not_import_quart():
    assert _violations("api/db/services", ("quart", "quart_schema", "quart_cors")) == []


def test_models_do_not_import_upper_layers():
    assert _violations("api/db/models", ("api.apps", "api.db.services")) == []


def test_detector_flags_a_violation(tmp_path, monkeypatch):
    bad = tmp_path / "x.py"
    bad.write_text("from api.db.models.base import BaseModel\nimport peewee\n")
    assert {"api.db.models.base.BaseModel", "peewee"} <= _imports(bad)


# --- Phase 3 packages (03-01): rag/ and the adapters stay free of the web framework and the API layer ---
def test_rag_never_imports_the_web_framework_or_the_handlers():
    assert _violations("rag", ("api.apps", "quart", "quart_schema", "quart_cors")) == []


def test_rag_utils_and_llm_do_not_import_the_database_layer():
    # rag/svr alone may import api.db (R-154); the adapters stay free of it.
    assert _violations("rag/utils", ("api.db",)) == []
    assert _violations("rag/llm", ("api.db",)) == []


def test_pure_rag_packages_import_nothing_from_api():
    # R-154: parsers, chunking, nlp and queue import neither api nor quart.
    for package in ("rag/parsers", "rag/chunking", "rag/nlp", "rag/queue"):
        assert _violations(package, ("api", "quart", "quart_schema", "quart_cors")) == [], package


def test_doc_store_and_net_do_not_import_api_rag_or_quart():
    forbidden = ("api", "rag", "quart", "quart_schema", "quart_cors")
    assert _violations("common/doc_store", forbidden) == []
    assert _violations("common/net", forbidden) == []


def test_new_packages_exist():
    for package in ("rag", "rag/utils", "common/doc_store", "common/net", "rag/parsers", "rag/chunking", "rag/nlp"):
        assert (ROOT / package / "__init__.py").is_file(), package
