# Phase 4: Ingestion Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-10
**Phase:** 04-ingestion-pipeline
**Areas discussed:** Starting and re-parsing, Failure, retry and cancel, Chunk editing rules, Files this phase can't parse

Each area's questions were asked together in one step instead of one at a time. The per-area "more questions?" check was replaced by one closing check.

---

## Starting and re-parsing

**When does parsing start for a newly uploaded document?**

| Option | Description | Selected |
|--------|-------------|----------|
| Only on Parse click | Documents wait at "Not started" until someone presses Parse; no embedding cost without a deliberate action | ✓ |
| Automatically after upload | Every upload is queued at once | |
| Per-dataset setting | A "parse on upload" switch, off by default | |

**In a team dataset, who may start, cancel and re-parse a document?**

| Option | Description | Selected |
|--------|-------------|----------|
| Uploader and managers | The uploader, the dataset's creator, the workspace owner and admins | ✓ |
| Any member | Anyone who can see the dataset | |
| Managers only | Creator, owner and admins | |

**What happens to edited or hand-added chunks on re-parse?**

| Option | Description | Selected |
|--------|-------------|----------|
| Replace all, warn first | Re-parse rebuilds from the file; the confirmation states how many hand-made changes will be lost | ✓ |
| Keep hand-added chunks | Hand-added chunks survive; edits are still lost | |
| Block re-parse if edited | Hand edits must be discarded explicitly first | |

**Should re-parsing a document that has chunks ask for confirmation?**

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, always | Names the document and its chunk count | ✓ |
| Only when hand edits exist | Otherwise starts at once | |
| No confirmation | Starts immediately | |

**User's choice:** the recommended option in all four.

---

## Failure, retry and cancel

**How many attempts before a document is marked failed?**

| Option | Description | Selected |
|--------|-------------|----------|
| 3 attempts | One try plus two automatic retries; configurable | ✓ |
| 5 attempts | More tolerant, costlier for a poison file | |
| 1 attempt, no auto-retry | Any failure fails at once | |

**What happens to chunks already indexed when a parse is cancelled or fails part-way?**

| Option | Description | Selected |
|--------|-------------|----------|
| Remove them (recommended) | Document ends with 0 chunks; totals rolled back | |
| Keep them searchable | Whatever was indexed stays and can be found | ✓ |
| Keep but hide from search | Kept in the inspector, marked unavailable | |

**What does a user see when a document fails?**

| Option | Description | Selected |
|--------|-------------|----------|
| Short reason plus details | Failed badge with a plain reason; details panel with the failing step and progress log; no stack traces | ✓ |
| Short reason only | Badge and one line | |
| Full technical log | Raw error trace in the UI | |

**How does the user try again after a failure or cancel?**

| Option | Description | Selected |
|--------|-------------|----------|
| Parse again, no confirm | Starts at once | ✓ |
| Parse again with confirm | Always through the dialog | |
| Re-upload required | Delete and upload again | |

**User's choice:** recommended options, except "Keep them searchable" for partial work.
**Notes:** Keeping partial chunks conflicted with "Parse again, no confirm", whose rationale assumed no chunks remained. A follow-up question settled it.

**Follow-up: how do kept partial chunks and Parse again fit together?**

| Option | Description | Selected |
|--------|-------------|----------|
| Mark as partial; confirm only if hand edits | "Partly indexed" label with chunk count; Parse again starts at once unless hand edits would be lost | ✓ |
| Mark as partial; never confirm | Parse again always starts at once | |
| Mark as partial; always confirm | Parse again always confirms | |

---

## Chunk editing rules

**Who may edit, add and switch chunks or a whole document on or off?**

| Option | Description | Selected |
|--------|-------------|----------|
| Uploader and managers | Same people who may parse | ✓ |
| Any member | Anyone who can see the dataset | |
| Managers only | Creator, owner and admins | |

**If the embedding call for an edit fails, what happens to the edit?**

| Option | Description | Selected |
|--------|-------------|----------|
| Refuse and keep the old chunk | Save refused with the reason; previous text and vector stay | ✓ |
| Save text, hide until embedded | New text saved, chunk off for search until re-embedded | |

**How should a switched-off chunk appear in the inspector?**

| Option | Description | Selected |
|--------|-------------|----------|
| Visible, dimmed, with a filter | Stays in place with an "Off" badge; filter for all, on, off | ✓ |
| Visible, dimmed, no filter | Same without the filter | |
| Hidden unless asked | Behind a "show switched-off chunks" toggle | |

**User's choice:** the recommended option in all three.

---

## Files this phase can't parse

**What should happen with uploaded types that have no parser in this phase?**

| Option | Description | Selected |
|--------|-------------|----------|
| Text-like as plain text; refuse the rest | Markdown, CSV and JSON use the TXT parser; images and others show "Parsing not available yet" | ✓ |
| Refuse all of them | Only the roadmap's six formats parse | |
| Let them fail | Parse offered for every file; unsupported ones end as Failed | |

**What should parsing a scanned PDF do?**

| Option | Description | Selected |
|--------|-------------|----------|
| Skip empty pages, fail if none | Text pages parsed, others counted in the log; no text at all fails at once, not retried | ✓ |
| Fail the whole document | Any page without text fails it | |
| Finish with what was found | Always Finished, even with 0 chunks | |

**How should the seven chunking methods not built yet appear?**

| Option | Description | Selected |
|--------|-------------|----------|
| Listed but unavailable | Shown with "Available in a later release"; API also refuses them | ✓ |
| Show only General | One method in the dialog | |
| All selectable, refused on save | Server refusal shown on save | |

**How large should the live test documents be?**

| Option | Description | Selected |
|--------|-------------|----------|
| Tiny, purpose-built | One 13+ page text PDF and one small file per format; a few dozen chunks per run | ✓ |
| One realistic document too | Adds a real PDF of about 50 pages | |
| You decide | Left to research and planning | |

**User's choice:** the recommended option in all four.

---

## Claude's Discretion

The user chose "I'm ready for context" rather than exploring further areas. Left to research and planning: chunk ID construction (R-11), the Redis lock design (R-12), how live the progress display is, how hand edits are recorded for counting, what preview and thumbnails cover, worker settings, page layout (UI design contract), and which Phase 3 review findings in touched code are fixed here.

## Deferred Ideas

- Parse-on-upload as a per-dataset setting
- OCR, layout analysis, table recognition, proper Markdown and table handling, the other seven chunkers (Phase 6)
- A "pending" state for chunks whose embedding failed
- A realistic 50-page live test document
- Remaining Phase 3 code-review warnings not touched by this phase
