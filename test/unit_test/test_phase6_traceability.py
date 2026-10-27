"""Phase 6 scope, feature ownership, and opt-in runtime exit checks."""

import json
import os
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
PHASE = ROOT / ".planning/phases/06-deep-parsing-and-chunking-breadth"
RANGES = [("PARSE", 4, 9), ("PARSE", 11, 11), ("PARSE", 14, 26),
          ("CHUNK", 3, 15), ("CHUNK", 17, 17), ("CHUNK", 22, 28),
          ("LLM", 10, 11), ("LLM", 13, 13), ("LLM", 32, 32),
          ("STOR", 9, 9), ("DOC", 17, 19), ("KB", 10, 13), ("KB", 17, 17),
          ("ING", 18, 18), ("DEPLOY", 8, 8), ("SEC", 8, 8), ("UI", 14, 14)]
REQUIREMENTS = {f"{prefix}-{number:02d}" for prefix, first, last in RANGES for number in range(first, last + 1)}
METHODS = {"naive", "paper", "book", "laws", "presentation", "table", "qa", "resume",
           "picture", "manual", "email", "tag", "one", "audio"}
OPTIONAL_BACKENDS = {"docling", "mineru", "paddleocr", "mistral", "tcadp", "somark", "opendataloader", "figure"}
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
ROUTES = {("GET", "/api/v1/pipelines"), ("GET", "/api/v1/pipelines/{id}"),
          ("GET", "/api/v1/datasets/{id}/tags"), ("DELETE", "/api/v1/datasets/{id}/tags"),
          ("GET", "/api/v1/datasets/tags/aggregation"), ("PATCH", "/api/v1/datasets/{id}/documents/metadatas"),
          ("GET", "/api/v1/datasets/metadata/flattened"), ("GET", "/api/v1/datasets/{id}/metadata/config"),
          ("GET", "/api/v1/documents/images/{id}"), ("GET", "/api/v1/documents/artifact/{id}"),
          ("POST", "/api/v1/datasets/{id}/jobs"), ("GET", "/api/v1/datasets/{id}/jobs"),
          ("GET", "/api/v1/datasets/{id}/jobs/{id}"), ("POST", "/api/v1/datasets/{id}/jobs/{id}/cancel"),
          ("DELETE", "/api/v1/datasets/{id}/{id}"), ("GET", "/api/v1/datasets/{id}/artifacts/alteration")}


def plans():
    return sorted(PHASE.glob("06-[0-9][0-9]-PLAN.md"))


def metadata(path):
    match = FRONTMATTER.match(path.read_text())
    assert match, path.name
    return yaml.safe_load(match[1])


def test_exact_scope_and_handoff_have_non_gate_feature_owners():
    assert len(REQUIREMENTS) == 58
    assert {row["id"] for row in json.loads((PHASE / "06-REQUIREMENT-SCOPE.json").read_text())} == REQUIREMENTS
    files = plans()
    assert len(files) == 30
    owned = set().union(*(set(metadata(path)["requirements"]) for path in files[1:-1]))
    assert REQUIREMENTS | {"RETR-13"} <= owned


def test_declared_methods_and_optional_backends_have_concrete_feature_inventory():
    scope = (PHASE / "06-SOURCE-AUDIT.md").read_text().lower()
    bodies = "\n".join(path.read_text().lower() for path in plans()[1:-1])
    for name in METHODS | OPTIONAL_BACKENDS:
        assert re.search(rf"\b{re.escape(name)}\b", bodies), name
        assert name in scope or name in (PHASE / "06-CONTRACTS.md").read_text().lower()


@pytest.mark.skipif(os.environ.get("PHASE6_GATE") != "1", reason="Phase 6 exit only: PHASE6_GATE=1")
def test_phase6_routes_methods_and_backends_are_reachable_at_exit():
    from common.ingest_codes import METHOD_ORDER
    from rag.chunking.factory import available

    assert METHODS <= set(METHOD_ORDER)
    assert all(available(name) for name in METHODS)
    registry = yaml.safe_load((ROOT / "conf/routes.yaml").read_text())["endpoints"]
    def normalize(path):
        return re.sub(r"\{[^}]+\}|<[^>]+>", "{id}", path)
    actual = {(row["method"], normalize(row["path"])): row for row in registry}
    for method, path in ROUTES:
        row = actual.get((method, path))
        assert row and row.get("implemented") is True, (method, path)
        if path.startswith("/api/v1/pipelines"):
            assert row["owner"] == "go" and row["auth"] == "none"
        else:
            assert row["owner"] == "python" and row["auth"] != "none"


@pytest.mark.skipif(os.environ.get("PHASE6_GATE") != "1", reason="Phase 6 exit only: PHASE6_GATE=1")
def test_all_prior_execution_plans_have_summaries():
    missing = [path.name for path in plans()[:-1] if not path.with_name(path.name.replace("-PLAN", "-SUMMARY")).is_file()]
    assert not missing, missing
