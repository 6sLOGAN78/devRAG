---
status: partial
phase: 03-models-knowledge-bases-and-upload
source: [03-VERIFICATION.md]
started: 2026-10-10T01:08:59Z
updated: 2026-10-10T01:08:59Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. File and folder drops in a headed browser
expected: Dropping a file on the page header (outside the dataset drop area) does not make the browser open the file. Dropping a folder on the dataset page is ignored and no upload starts.
result: [pending]

### 2. Focus return after dialogs
expected: After the upload dialog, the dataset settings dialog and the delete dialogs close, keyboard focus returns to the control that opened them (or to the page title after a delete removes that control).
result: [pending]

### 3. Visual and accessibility pass in light and dark theme
expected: The model settings page, datasets gallery, dataset page and upload dialog look right and are usable by keyboard in both themes. The model settings page has been covered by jsdom and live API-client tests only, not rendered in real Chrome.
result: [pending]

### 4. Chinese copy review
expected: A Chinese reader confirms the draft strings in web/src/locales/zh.json for the Phase 3 pages read correctly (B-18).
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
