"""Phase 5 traceability (plan 05-01): requirements, decisions, registry rows and summaries are machine-checked.

* every requirement ID of the phase appears in the ``requirements:`` list of at least one Phase 5 plan;
* every decision D-01..D-26 is cited by id inside the ``must_haves`` block of at least one plan;
* with ``PHASE5_GATE=1`` every executed plan also has its SUMMARY and every Phase 5 route in the registry is
  ``implemented: true`` (phase exit). Without the variable only the plan-file checks run, so the test passes while
  plans are still being executed.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / ".planning" / "phases" / "05-retrieval-and-cited-chat-core-value-gate"
ROUTES = ROOT / "conf" / "routes.yaml"

REQUIREMENT_RANGES: list[tuple[str, int, int]] = [
    ("RETR", 1, 19), ("RETR", 23, 23),
    ("CHAT", 1, 23), ("CHAT", 31, 31),
    ("LLM", 9, 9),
    ("ING", 21, 21),
    ("TEN", 3, 3),
    ("KB", 18, 18),
    ("UI", 5, 5), ("UI", 18, 18), ("UI", 20, 25),
    ("DEPLOY", 18, 18),
    ("E2E", 7, 9), ("E2E", 12, 12),
]
REQUIREMENT_IDS = [f"{prefix}-{n:02d}" for prefix, first, last in REQUIREMENT_RANGES for n in range(first, last + 1)]
DECISION_IDS = [f"D-{n:02d}" for n in range(1, 27)]
ROUTE_PREFIXES = ("/api/v1/chats", "/api/v1/chat/", "/api/v1/datasets/search")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def plan_files() -> list[Path]:
    return sorted(PHASE_DIR.glob("05-[0-9][0-9]-PLAN.md"))


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
    assert len(names) >= 28, names
    assert "05-01-PLAN.md" in names


def test_requirement_list_is_expanded_correctly() -> None:
    assert len(REQUIREMENT_IDS) == len(set(REQUIREMENT_IDS)) == 61
    by_prefix = {p: sum(1 for r in REQUIREMENT_IDS if r.startswith(p + "-")) for p in ("RETR", "CHAT", "LLM", "ING", "TEN", "KB", "UI", "DEPLOY", "E2E")}
    assert by_prefix == {"RETR": 20, "CHAT": 24, "LLM": 1, "ING": 1, "TEN": 1, "KB": 1, "UI": 8, "DEPLOY": 1, "E2E": 4}
    assert "RETR-23" in REQUIREMENT_IDS and "CHAT-31" in REQUIREMENT_IDS and "E2E-12" in REQUIREMENT_IDS
    assert "RETR-20" not in REQUIREMENT_IDS and "CHAT-24" not in REQUIREMENT_IDS and "E2E-10" not in REQUIREMENT_IDS
    assert len(DECISION_IDS) == 26


def test_every_phase_requirement_is_claimed_by_a_plan() -> None:
    covered: set[str] = set()
    for path in plan_files():
        covered |= requirements_of(path)
    missing = [rid for rid in REQUIREMENT_IDS if rid not in covered]
    assert not missing, f"requirements not in any 05-NN-PLAN.md frontmatter: {missing}"


def test_every_decision_is_cited_in_a_plans_must_haves() -> None:
    blocks = [must_haves_block(path) for path in plan_files()]
    missing = [did for did in DECISION_IDS if not any(re.search(rf"\b{did}\b", block) for block in blocks)]
    assert not missing, f"decisions not cited in any must_haves block: {missing}"


@pytest.mark.skipif(os.environ.get("PHASE5_GATE") != "1", reason="checked at phase exit only: PHASE5_GATE=1")
def test_every_phase5_endpoint_is_implemented() -> None:
    registry = yaml.safe_load(ROUTES.read_text()).get("endpoints") or []
    rows = [row for row in registry if str(row["path"]).startswith(ROUTE_PREFIXES)]
    assert len(rows) >= 11, "the registry has the Phase 5 rows"
    pending = [f"{row['method']} {row['path']}" for row in rows if row.get("implemented") is not True]
    assert not pending, f"registry rows not implemented: {pending}"


@pytest.mark.skipif(os.environ.get("PHASE5_GATE") != "1", reason="checked at phase exit only: PHASE5_GATE=1")
def test_every_executed_plan_has_a_summary() -> None:
    missing = [
        path.name.replace("-PLAN", "-SUMMARY")
        for path in plan_files()
        if path.name != "05-28-PLAN.md"  # This gate cannot require its own not-yet-written summary.
        and not path.with_name(path.name.replace("-PLAN", "-SUMMARY")).exists()
    ]
    assert not missing, f"plans without a SUMMARY: {missing}"
