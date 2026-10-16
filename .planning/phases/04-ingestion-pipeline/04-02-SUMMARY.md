---
phase: 04-ingestion-pipeline
plan: 02
subsystem: infra
tags: [uv, supply-chain, pypdfium2, pillow, python-docx, python-pptx, openpyxl, lxml, beautifulsoup4]
requires:
  - phase: 03-datasets
    provides: uv-locked Python project with warnings-as-errors pytest config
provides:
  - Seven approved parsing libraries hash-locked at exact pins
  - charset-normalizer as a direct dependency
  - 04-PACKAGES.md registry and OSV audit with the recorded human decision
  - Import smoke and pin/forbidden-package test
affects: [04-08, 04-09, parser plans]
tech-stack:
  added: [pypdfium2 5.13.0, pillow 12.3.0, python-docx 1.2.0, python-pptx 1.0.2, openpyxl 3.1.5, lxml 6.1.3, beautifulsoup4 4.15.0, soupsieve 2.10, charset-normalizer 3.5.2 (direct)]
  patterns: [registry and OSV audit then blocking human gate before any install]
key-files:
  created:
    - .planning/phases/04-ingestion-pipeline/04-PACKAGES.md
    - test/unit_test/test_phase4_packages.py
  modified:
    - pyproject.toml
    - uv.lock
key-decisions:
  - "pypdfium2 pinned to 5.13.0, not 5.14.0 (human answer: 5.14.0 was 13 days old)"
  - "soupsieve held below 3 with a direct constraint, resolves to 2.10 (3.0.x was days old)"
  - "chardet not added; charset-normalizer 3.5.2 (already locked) made direct (D-28)"
requirements-completed: []
duration: n/a
completed: 2026-10-17
---

# Phase 4 Plan 02: Parsing package audit and install Summary

Seven parsing libraries audited against PyPI and OSV, approved by a human at a blocking gate, then installed at exact hash-locked pins with soupsieve held below 3 and pypdfium2 on 5.13.0.

## Tasks

| Task | Name | Commit |
|---|---|---|
| 1 | Registry audit table | b143874 |
| 2 | Human checkpoint (answered: "approved, pin soupsieve<3 and use pypdfium2==5.13.0") | dc0b588 (records the answer) |
| 3 RED | Failing pin/import tests | d9873ac |
| 3 GREEN | Install at exact pins | a12e044 |

## Resolved versions

pypdfium2 5.13.0, pillow 12.3.0, python-docx 1.2.0, python-pptx 1.0.2, openpyxl 3.1.5, lxml 6.1.3, beautifulsoup4 4.15.0, soupsieve 2.10, charset-normalizer 3.5.2, plus transitive et-xmlfile 2.0.0 and xlsxwriter 3.2.9. OSV reported no advisory for any of them.

## Verification

- `uv run python -m pytest test/unit_test/test_phase4_packages.py -q`: 25 passed
- `uv lock --check`: exit 0
- `uv run python -W error -c "import pypdfium2, PIL, docx, pptx, openpyxl, bs4, lxml.etree"`: exit 0
- `git diff uv.lock`: only additions of the ten new packages; no existing package changed (no litellm, openai, elasticsearch, valkey line)
- `web/package.json` and `web/package-lock.json`: unchanged

## Deviations from Plan

1. **Pins changed by the human at the checkpoint (not an auto-fix):** pypdfium2 5.13.0 instead of 5.14.0; added direct `soupsieve<3` (2.10, uploaded 2026-09-24, MIT, no OSV advisory). Both re-audited and recorded in 04-PACKAGES.md.
2. **[Rule 3 - minor] Pillow spelling:** `uv add` wrote `pillow==12.3.0` (lower case) in `pyproject.toml`, so the plan's case-sensitive grep for `Pillow==` matches six lines, not seven. The package and pin are correct; the test compares names case-insensitively.
3. `pypdfium2_raw` has no audit row because pypdfium2 5.x does not depend on it.

## Auth gates

None. The package legitimacy checkpoint was handled as a normal blocking gate and answered by the human.

## Known Stubs

None.

## Threat Flags

None. No new network, auth or file-access surface.

## Self-Check: PASSED

Files exist (04-PACKAGES.md, test_phase4_packages.py); commits b143874, dc0b588, d9873ac, a12e044 present in git log.
