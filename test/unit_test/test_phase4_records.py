"""Phase 4 records: decision rows R-154..R-167 exist and are well formed, R-11 is resolved by R-155,
the four partially delivered requirements are marked in both records, and the layering carve-out is stated."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

FIRST_ROW = 154
LAST_ROW = 167
STATUS = "accepted (auto, not user-reviewed)"
ROW = re.compile(r"^\| R-(\d+) \|")

# One substring per decision Phase 4 had to take beyond docs/. Each must appear in exactly one row title.
REQUIRED_TITLES = [
    "Executor layering",
    "Chunk ids and chunk fields",
    "Task lock, reclaim and consumer names",
    "Valkey as a queue",
    "Attempts, failure classes and cancel",
    "Counters set to truth",
    "Tokenizer and partial requirements",
    "Phase 4 packages and encoding",
    "Phase 4 API shape",
    "Document switch, chunk switch",
    "Frontend routes and delivery",
    "Ingest configuration",
    "Phase 3 findings taken on",
    "SPA locale areas and test-server areas",
]

PARTIAL_IDS = ["CHUNK-17", "PARSE-09", "PARSE-11", "UI-14"]


def _all_rows(repo_root: Path) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for line in (repo_root / ".planning" / "DECISIONS.md").read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if m:
            out.setdefault(int(m.group(1)), []).append(line)
    return out


def _rows(repo_root: Path) -> dict[int, list[str]]:
    return {n: lines for n, lines in _all_rows(repo_root).items() if n >= FIRST_ROW}


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split(" | ")]


def test_every_phase4_row_exists_once_and_is_well_formed(repo_root):
    rows = _rows(repo_root)
    missing = [f"R-{n}" for n in range(FIRST_ROW, LAST_ROW + 1) if n not in rows]
    assert not missing, f"missing decision rows: {missing}"
    for n in range(FIRST_ROW, LAST_ROW + 1):
        assert len(rows[n]) == 1, f"R-{n} appears {len(rows[n])} times"
        cells = _cells(rows[n][0])
        assert len(cells) == 5, f"R-{n}: expected 5 cells, got {len(cells)}"
        assert cells[1], f"R-{n}: empty title"
        assert cells[2], f"R-{n}: empty resolution"
        assert cells[3] == STATUS, f"R-{n}: status is {cells[3]!r}"
        assert cells[4], f"R-{n}: empty source"
        assert not re.search(r"\bproposed\b", rows[n][0], re.I), f"R-{n}: contains 'proposed'"


def test_titles_cover_every_phase4_decision(repo_root):
    rows = _rows(repo_root)
    titles = [_cells(rows[n][0])[1] for n in range(FIRST_ROW, LAST_ROW + 1) if n in rows]
    for needle in REQUIRED_TITLES:
        hits = [t for t in titles if needle.lower() in t.lower()]
        assert len(hits) == 1, f"title substring {needle!r} matches {len(hits)} Phase 4 rows"


def test_r11_is_resolved_by_r155(repo_root):
    rows = _all_rows(repo_root)[11]
    assert len(rows) == 1
    cells = _cells(rows[0])
    assert cells[3] != "open", "R-11 is still open"
    assert "R-155" in cells[2], "R-11 does not point at R-155"


def test_partial_requirements_and_phase6_hand_off_are_recorded(repo_root):
    requirements = (repo_root / ".planning" / "REQUIREMENTS.md").read_text(encoding="utf-8").splitlines()
    for ident in PARTIAL_IDS:
        lines = [ln for ln in requirements if ident in ln and re.search(r"partial", ln, re.I)]
        assert lines, f"REQUIREMENTS.md has no 'partial' note for {ident}"
    roadmap = (repo_root / ".planning" / "ROADMAP.md").read_text(encoding="utf-8")
    m = re.search(r"Moved from Phase 4 \(D-27\):[^\n]*", roadmap)
    assert m, "ROADMAP.md has no 'Moved from Phase 4' line"
    for needle in ("traditional-to-simplified", "dictionary Chinese tokenizer", "DOCX and PPTX", "layout toggle", "auto-keyword"):
        assert needle in m.group(0), f"Phase 6 hand-off line does not name {needle!r}"
    phase6 = roadmap.index("Phase 6")
    assert roadmap.index("Moved from Phase 4") > phase6


def test_r154_states_the_layering_carve_out(repo_root):
    cell = _cells(_rows(repo_root)[154][0])[2]
    assert "rag/svr" in cell and "api.db" in cell and "api.apps" in cell and "quart" in cell
