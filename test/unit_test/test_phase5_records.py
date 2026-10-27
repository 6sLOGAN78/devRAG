"""Phase 5 records: decision rows R-192..R-231 exist, are contiguous and well formed, and R-26 / R-27 point at them.

Later Phase 5 plans append their own titles to REQUIRED_TITLES in the plan that adds the row; the gate plan pins
the final count.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

FIRST_ROW = 192
LAST_ROW = 231
STATUS = "accepted (auto, not user-reviewed)"
ROW = re.compile(r"^\| R-(\d+) \|")

# One substring per decision Phase 5 had to take beyond docs/. Each must appear in exactly one row title.
REQUIRED_TITLES = [
    "SSE framing",
    "Citation marker numbering",
    "Retrieval route",
    "Similarity semantics",
    "Query building",
    "Rerank failure",
    "Assistant schema",
    "Chat permissions",
    "Unavailable datasets",
    "Stopped-turn usage",
    "Live budget and planted facts",
    "Retrieval settings and synonyms",
    "Condition `must_not` and stage-2 kNN",
    "Retrieval-test limits and shape",
    "TEI provider and rerank type",
    "OpenRouter rerank driver",
    "Calibration result",
    "Assistant rules as built",
    "Assistant view keys",
    "Chat routes and Nginx families",
    "Sessions, turn lock, redaction and feedback route",
    "Prompt, context and injection stance",
    "Turn orchestration and BE-07",
    "Stream deadline and stop persistence",
    "8B citation adherence and model choice",
    "Phase 5 packages and image outcome",
    "TEI image and volume",
    "R-52 closed",
    "SPA services and SSE client",
    "Answer rendering rules",
    "Assistant dialog rules",
    "Chat page routes, draft chat and deletion placement",
    "Turn UI states",
    "Source drawer and feedback",
    "Retrieval testing page",
    "Live tier results",
    "Criterion-5 journey",
    "Sharing journeys",
    "Partial requirements and hand-offs",
    "Phase 5 gate result",
]


def _all_rows(repo_root: Path) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for line in (repo_root / ".planning" / "DECISIONS.md").read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if m:
            out.setdefault(int(m.group(1)), []).append(line)
    return out


def _rows(repo_root: Path) -> dict[int, list[str]]:
    return {n: lines for n, lines in _all_rows(repo_root).items() if FIRST_ROW <= n <= LAST_ROW}


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split(" | ")]


def test_phase5_rows_are_contiguous_and_well_formed(repo_root):
    rows = _rows(repo_root)
    assert rows, "no Phase 5 decision rows"
    highest = max(rows)
    assert highest == LAST_ROW, f"highest Phase 5 row is R-{highest}, expected R-{LAST_ROW}"
    missing = [f"R-{n}" for n in range(FIRST_ROW, highest + 1) if n not in rows]
    assert not missing, f"missing decision rows: {missing}"
    for n in range(FIRST_ROW, highest + 1):
        assert len(rows[n]) == 1, f"R-{n} appears {len(rows[n])} times"
        cells = _cells(rows[n][0])
        assert len(cells) == 5, f"R-{n}: expected 5 cells, got {len(cells)}"
        assert cells[1], f"R-{n}: empty title"
        assert cells[2], f"R-{n}: empty resolution"
        assert cells[3] == STATUS, f"R-{n}: status is {cells[3]!r}"
        assert cells[4], f"R-{n}: empty source"
        assert not re.search(r"\bproposed\b", rows[n][0], re.I), f"R-{n}: contains 'proposed'"


def test_titles_cover_every_phase5_decision(repo_root):
    rows = _rows(repo_root)
    titles = [_cells(rows[n][0])[1] for n in sorted(rows)]
    for needle in REQUIRED_TITLES:
        hits = [t for t in titles if needle.lower() in t.lower()]
        assert len(hits) == 1, f"title substring {needle!r} matches {len(hits)} Phase 5 rows"


def test_r26_is_closed_by_r192_and_r27_refined_by_r193(repo_root):
    everything = _all_rows(repo_root)
    r192 = " ".join(_rows(repo_root)[192])
    r193 = " ".join(_rows(repo_root)[193])
    assert "R-26" in r192, "R-192 does not mention R-26"
    assert "R-27" in r193, "R-193 does not mention R-27"
    r26 = _cells(everything[26][0])
    assert r26[3] == STATUS, f"R-26 status is {r26[3]!r}"
    assert "Closed by R-192" in r26[2], "R-26 does not point at R-192"
    assert "Refined by R-193" in everything[27][0], "R-27 does not point at R-193"


PARTIAL_IDS = ["RETR-03", "RETR-04", "RETR-09", "RETR-13", "RETR-16", "CHAT-05", "LLM-09", "ING-21", "UI-22", "UI-25"]


def test_partial_requirements_are_marked_in_both_records(repo_root):
    row = _rows(repo_root)[230][0]
    roadmap = (repo_root / ".planning/ROADMAP.md").read_text()
    note = next(line for line in roadmap.splitlines() if line.startswith("Partial requirements (hand-offs"))
    assert all(item in row and item in note for item in PARTIAL_IDS)
