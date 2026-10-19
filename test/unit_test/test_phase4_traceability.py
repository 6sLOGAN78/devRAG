"""Phase 4 traceability (plan 04-35): requirements, decisions, registry rows and summaries are machine-checked.

* every requirement ID of the phase appears in the ``requirements:`` list of at least one Phase 4 plan;
* every decision D-01..D-31 is cited by id inside the ``must_haves`` block of at least one plan;
* every registry row for the Phase 4 routes is ``implemented: true``;
* with ``PHASE4_GATE=1`` every executed plan also has its SUMMARY (phase exit).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / ".planning" / "phases" / "04-ingestion-pipeline"
ROUTES = ROOT / "conf" / "routes.yaml"
SELF_PLAN = "04-35-PLAN.md"

REQUIREMENT_RANGES: list[tuple[str, int, int]] = [
    ("ING", 1, 16),
    ("PARSE", 1, 3), ("PARSE", 9, 13),
    ("CHUNK", 1, 2), ("CHUNK", 16, 21),
    ("IDX", 1, 3), ("IDX", 7, 7), ("IDX", 14, 14),
    ("DOC", 9, 13), ("DOC", 20, 23),
    ("KB", 14, 16), ("KB", 19, 19),
    ("UI", 13, 17), ("UI", 19, 19),
    ("DEPLOY", 17, 17),
    ("TEST", 11, 11),
    ("E2E", 5, 6),
]
REQUIREMENT_IDS = [f"{prefix}-{n:02d}" for prefix, first, last in REQUIREMENT_RANGES for n in range(first, last + 1)]
DECISION_IDS = [f"D-{n:02d}" for n in range(1, 32)]
ROUTE_MARKERS = (
    "/documents/parse", "/batch-update-status", "/documents/{doc_id}", "/chunks", "/pages/",
    "/content", "/ingestions", "/embedding/check", "/v1/task/status",
)
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def plan_files() -> list[Path]:
    return sorted(PHASE_DIR.glob("04-[0-9][0-9]-PLAN.md"))


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
    assert len(names) >= 31, names
    assert SELF_PLAN in names


def test_requirement_list_is_expanded_correctly() -> None:
    assert len(REQUIREMENT_IDS) == len(set(REQUIREMENT_IDS)) == 60
    assert "ING-16" in REQUIREMENT_IDS and "PARSE-09" in REQUIREMENT_IDS and "E2E-06" in REQUIREMENT_IDS
    assert "PARSE-04" not in REQUIREMENT_IDS and "CHUNK-03" not in REQUIREMENT_IDS and "UI-18" not in REQUIREMENT_IDS
    assert len(DECISION_IDS) == 31


def test_every_phase_requirement_is_claimed_by_a_plan() -> None:
    covered: set[str] = set()
    for path in plan_files():
        covered |= requirements_of(path)
    missing = [rid for rid in REQUIREMENT_IDS if rid not in covered]
    assert not missing, f"requirements not in any 04-NN-PLAN.md frontmatter: {missing}"


def test_every_decision_is_cited_in_a_plans_must_haves() -> None:
    blocks = [must_haves_block(path) for path in plan_files()]
    missing = [did for did in DECISION_IDS if not any(re.search(rf"\b{did}\b", block) for block in blocks)]
    assert not missing, f"decisions not cited in any must_haves block: {missing}"


def test_every_phase4_endpoint_is_implemented() -> None:
    registry = yaml.safe_load(ROUTES.read_text()).get("endpoints") or []
    rows = [row for row in registry if any(marker in str(row["path"]) for marker in ROUTE_MARKERS)]
    assert len(rows) >= 9, "the registry has the Phase 4 rows"
    pending = [f"{row['method']} {row['path']}" for row in rows if row.get("implemented") is not True]
    assert not pending, f"registry rows not implemented: {pending}"


@pytest.mark.skipif(os.environ.get("PHASE4_GATE") != "1", reason="checked at phase exit only: PHASE4_GATE=1")
def test_every_executed_plan_has_a_summary() -> None:
    missing = [
        path.name.replace("-PLAN", "-SUMMARY")
        for path in plan_files()
        if path.name != SELF_PLAN and not path.with_name(path.name.replace("-PLAN", "-SUMMARY")).exists()
    ]
    assert not missing, f"plans without a SUMMARY: {missing}"
