"""Bounded Phase 6 decision records and regression protection for prior phases."""

import re
from pathlib import Path

import pytest

from test.unit_test import test_phase5_records as phase5

pytestmark = pytest.mark.unit
FIRST_ROW = 232
LAST_ROW = 249  # Extended by the plan that actually records each decision.
FINAL_ROW = 261
STATUS = "accepted (auto, not user-reviewed)"
REQUIRED_TITLES = ["Phase 6 acquisition and admission", "CPU OCR service and native boundary", "Read scanned PDFs through the existing document UI", "Preserve visual reading order and remove page furniture", "Open extracted images and office figures securely", "Inspect reconstructed PDF tables and crops", "Choose whole-document chunks and inspect public pipeline templates", "Ingest Markdown and technical manuals", "Ingest structured JSON, CSV and Q&A pairs", "Read EPUB books in chapter order", "Read academic papers by section", "Read legal structure and normalize Chinese text", "Inspect presentation chunks per slide", "Retrieve table rows with their headers", "Caption pictures with a configured vision model", "Transcribe audio into timestamped chunks", "Read email envelopes and message bodies", "Read structured résumé sections"]
ROW = re.compile(r"^\| R-(\d+) \|")


def _rows(root: Path) -> dict[int, list[str]]:
    rows: dict[int, list[str]] = {}
    for line in (root / ".planning/DECISIONS.md").read_text().splitlines():
        match = ROW.match(line)
        if match and FIRST_ROW <= int(match[1]) <= FINAL_ROW:
            rows.setdefault(int(match[1]), []).append(line)
    return rows


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split(" | ")]


@pytest.mark.parametrize("future_row", [232, 261, 262])
def test_future_rows_do_not_change_phase5_assertions(repo_root, tmp_path, future_row):
    planning = tmp_path / ".planning"
    planning.mkdir()
    original = (repo_root / ".planning/DECISIONS.md").read_text()
    synthetic = f"\n| R-{future_row} | Future phase fixture | Separate scope | {STATUS} | Fixture |\n"
    (planning / "DECISIONS.md").write_text(original + synthetic)
    assert phase5._rows(tmp_path) == phase5._rows(repo_root)
    phase5.test_phase5_rows_are_contiguous_and_well_formed(tmp_path)
    phase5.test_titles_cover_every_phase5_decision(tmp_path)
    phase5.test_r26_is_closed_by_r192_and_r27_refined_by_r193(tmp_path)


def test_phase6_rows_are_contiguous_unique_and_well_formed(repo_root):
    rows = _rows(repo_root)
    assert set(rows) == set(range(FIRST_ROW, LAST_ROW + 1))
    for number, lines in rows.items():
        assert len(lines) == 1, f"R-{number} duplicated"
        cells = _cells(lines[0])
        assert len(cells) == 5 and all(cells)
        assert cells[3] == STATUS
        assert not re.search(r"\bproposed\b", lines[0], re.I)
    titles = [_cells(lines[0])[1] for lines in rows.values()]
    for title in REQUIRED_TITLES:
        assert sum(title.lower() in value.lower() for value in titles) == 1


def test_phase6_excludes_subsequent_phases(repo_root, tmp_path):
    (tmp_path / ".planning").mkdir()
    original = (repo_root / ".planning/DECISIONS.md").read_text()
    (tmp_path / ".planning/DECISIONS.md").write_text(
        original + f"\n| R-262 | Future phase | Separate scope | {STATUS} | Fixture |\n"
    )
    assert _rows(tmp_path) == _rows(repo_root)
