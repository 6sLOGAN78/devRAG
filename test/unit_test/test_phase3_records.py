"""Phase 3 records: decision rows R-136.. exist and are well formed, the litellm pin agrees everywhere,
the packages the stack table lists but Phase 3 does not use stay out of web/package.json, and B-09 is closed."""

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

FIRST_ROW = 136
LAST_ROW = 152  # the last Phase 3 row; later phases continue the numbering after it
STATUS = "accepted (auto, not user-reviewed)"
ROW = re.compile(r"^\| R-(\d+) \|")

# One substring per decision Phase 3 had to take beyond docs/. Each must appear in exactly one row title.
REQUIRED_TITLES = [
    "Index per tenant",
    "Credential system of record",
    "litellm",
    "react-dropzone",
    "Provider base URL",
    "Acting workspace",
    "Upload rules",
    "Dedupe",
    "Storage",
    "API conventions",
    "Live model tier",
    "Doc store port",
    "Log masking limit",
    "Usage counters",
    "Route generator",
    "Locale key prefixes",
    "Dialog stacking",
]


def _rows(repo_root: Path) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for line in (repo_root / ".planning" / "DECISIONS.md").read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if m:
            out.setdefault(int(m.group(1)), []).append(line)
    return {n: lines for n, lines in out.items() if n >= FIRST_ROW}


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split(" | ")]


def test_every_phase3_row_exists_once_and_is_well_formed(repo_root):
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


def test_titles_cover_every_phase3_decision(repo_root):
    rows = _rows(repo_root)
    titles = [_cells(rows[n][0])[1] for n in range(FIRST_ROW, LAST_ROW + 1) if n in rows]
    for needle in REQUIRED_TITLES:
        hits = [t for t in titles if needle.lower() in t.lower()]
        assert len(hits) == 1, f"title substring {needle!r} matches {len(hits)} Phase 3 rows"


def _pyproject_litellm(repo_root: Path) -> str:
    text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'"litellm==([0-9][0-9A-Za-z.]*)"', text)
    assert m, "pyproject.toml has no exact litellm pin"
    return m.group(1)


def test_litellm_pin_is_the_same_in_pyproject_lock_and_claude_md(repo_root):
    pinned = _pyproject_litellm(repo_root)

    lock = (repo_root / "uv.lock").read_text(encoding="utf-8")
    block = re.search(r'\[\[package\]\]\nname = "litellm"\nversion = "([^"]+)"', lock)
    assert block, "uv.lock has no litellm package block"
    assert block.group(1) == pinned, f"uv.lock locks litellm {block.group(1)}, pyproject pins {pinned}"

    claude = (repo_root / "CLAUDE.md").read_text(encoding="utf-8")
    stack = re.search(r"^\| LiteLLM \| (\S+) \(exact pin\)", claude, re.M)
    assert stack, "CLAUDE.md stack table has no LiteLLM exact-pin row"
    assert stack.group(1) == pinned, f"CLAUDE.md stack table says {stack.group(1)}, pyproject pins {pinned}"
    avoid = re.search(r"^\| litellm unpinned or `>=` .*`litellm==([0-9][0-9A-Za-z.]*)`", claude, re.M)
    assert avoid, "CLAUDE.md What NOT to Use table has no litellm row"
    assert avoid.group(1) == pinned, f"CLAUDE.md What NOT to Use says {avoid.group(1)}, pyproject pins {pinned}"

    # The old baseline may only be mentioned where the move away from it is explained.
    for line in claude.splitlines():
        if "1.84.0" in line:
            assert pinned in line, f"CLAUDE.md mentions the old 1.84.0 baseline without the move to {pinned}: {line[:80]}"


@pytest.mark.parametrize("package", ["react-dropzone", "@tanstack/react-table"])
def test_web_package_json_does_not_list_unused_stack_packages(repo_root, package):
    data = json.loads((repo_root / "web" / "package.json").read_text(encoding="utf-8"))
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        assert package not in (data.get(section) or {}), f"{package} is in web/package.json {section} (D-21)"


def _blocker(repo_root: Path, ident: str) -> str:
    text = (repo_root / ".planning" / "BLOCKERS.md").read_text(encoding="utf-8")
    m = re.search(rf"^## {ident} .*?(?=^## B-|\Z)", text, re.M | re.S)
    assert m, f"{ident} not found in BLOCKERS.md"
    return m.group(0)


def test_b09_is_closed_with_the_evidence(repo_root):
    entry = _blocker(repo_root, "B-09")
    assert re.search(r"^- Status: closed", entry, re.M), "B-09 is not closed"
    assert "OpenRouter" in entry and "D-01" in entry and "D-03" in entry


@pytest.mark.parametrize("ident", ["B-17", "B-21", "B-22"])
def test_earlier_open_blockers_stay_open(repo_root, ident):
    assert not re.search(r"^- Status: closed", _blocker(repo_root, ident), re.M)


@pytest.mark.parametrize("ident", ["B-31", "B-32", "B-33"])
def test_phase3_open_risks_are_recorded_as_open(repo_root, ident):
    assert re.search(r"^- Status: open", _blocker(repo_root, ident), re.M)
