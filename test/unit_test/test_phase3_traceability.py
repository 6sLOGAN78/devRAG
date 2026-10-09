"""Phase 3 traceability (plan 03-29): requirements, decisions, registry rows and summaries are machine-checked.

* every requirement ID of the phase appears in the ``requirements:`` list of at least one Phase 3 plan;
* every decision D-01..D-29 is cited by id inside the ``must_haves`` block of at least one plan;
* every registry row for providers, models, datasets and documents is ``implemented: true``;
* with ``PHASE3_GATE=1`` every executed plan also has its SUMMARY (phase exit).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / ".planning" / "phases" / "03-models-knowledge-bases-and-upload"
ROUTES = ROOT / "conf" / "routes.yaml"
SELF_PLAN = "03-29-PLAN.md"

# The Phase 3 requirement list of the roadmap: (prefix, first, last) ranges and single ids.
REQUIREMENT_RANGES: list[tuple[str, int, int]] = [
    ("LLM", 1, 5), ("LLM", 14, 29),
    ("KB", 1, 9),
    ("TEN", 12, 13), ("TEN", 16, 16),
    ("STOR", 1, 2), ("STOR", 6, 6), ("STOR", 8, 8), ("STOR", 10, 11),
    ("DOC", 1, 8), ("DOC", 14, 16),
    ("IDX", 4, 6), ("IDX", 8, 9),
    ("UI", 10, 12), ("UI", 37, 37),
    ("SEC", 2, 3), ("SEC", 6, 6),
    ("TEST", 8, 8),
    ("E2E", 3, 4),
]
REQUIREMENT_IDS = [f"{prefix}-{n:02d}" for prefix, first, last in REQUIREMENT_RANGES for n in range(first, last + 1)]
DECISION_IDS = [f"D-{n:02d}" for n in range(1, 30)]
REGISTRY_PREFIXES = ("/api/v1/providers", "/api/v1/models", "/api/v1/datasets", "/api/v1/documents")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def plan_files() -> list[Path]:
    return sorted(PHASE_DIR.glob("03-[0-9][0-9]-PLAN.md"))


def frontmatter_text(path: Path) -> str:
    match = FRONTMATTER.match(path.read_text())
    assert match, f"{path.name} has no frontmatter"
    return match.group(1)


def requirements_of(path: Path) -> set[str]:
    declared = yaml.safe_load(frontmatter_text(path)).get("requirements") or []
    return {str(item) for item in declared}


def must_haves_block(path: Path) -> str:
    text = frontmatter_text(path)
    start = text.find("must_haves:")
    return text[start:] if start >= 0 else ""


def test_the_phase_has_its_plans() -> None:
    names = [p.name for p in plan_files()]
    assert len(names) >= 29, names
    assert SELF_PLAN in names


def test_requirement_list_is_expanded_correctly() -> None:
    assert len(REQUIREMENT_IDS) == len(set(REQUIREMENT_IDS))
    assert "LLM-01" in REQUIREMENT_IDS and "LLM-05" in REQUIREMENT_IDS and "LLM-29" in REQUIREMENT_IDS
    assert "LLM-06" not in REQUIREMENT_IDS and "TEN-14" not in REQUIREMENT_IDS and "STOR-07" not in REQUIREMENT_IDS


def test_every_phase_requirement_is_claimed_by_a_plan() -> None:
    covered: set[str] = set()
    for path in plan_files():
        covered |= requirements_of(path)
    missing = [rid for rid in REQUIREMENT_IDS if rid not in covered]
    assert not missing, f"requirements not in any 03-NN-PLAN.md frontmatter: {missing}"


def test_every_decision_is_cited_in_a_plans_must_haves() -> None:
    blocks = [must_haves_block(path) for path in plan_files()]
    missing = [did for did in DECISION_IDS if not any(re.search(rf"\b{did}\b", block) for block in blocks)]
    assert not missing, f"decisions not cited in any must_haves block: {missing}"


def test_every_provider_model_dataset_and_document_endpoint_is_implemented() -> None:
    registry = yaml.safe_load(ROUTES.read_text()).get("endpoints") or []
    rows = [row for row in registry if str(row["path"]).startswith(REGISTRY_PREFIXES)]
    assert rows, "the registry has Phase 3 rows"
    pending = [f"{row['method']} {row['path']}" for row in rows if row.get("implemented") is not True]
    assert not pending, f"registry rows not implemented: {pending}"


@pytest.mark.skipif(os.environ.get("PHASE3_GATE") != "1", reason="checked at phase exit only: PHASE3_GATE=1")
def test_every_executed_plan_has_a_summary() -> None:
    missing = [
        path.name.replace("-PLAN", "-SUMMARY")
        for path in plan_files()
        if path.name != SELF_PLAN and not path.with_name(path.name.replace("-PLAN", "-SUMMARY")).exists()
    ]
    assert not missing, f"plans without a SUMMARY: {missing}"
