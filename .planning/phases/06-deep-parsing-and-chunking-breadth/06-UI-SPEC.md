---
phase: 6
slug: deep-parsing-and-chunking-breadth
status: reviewed_auto
created: 2026-10-27
inherits: 05-UI-SPEC.md
shadcn_initialized: true
preset: none
human_approval: not_claimed
---

# Phase 6 UI design contract

Generated inline under `gsd-ui-phase --auto`; no discuss-phase preference or human approval is invented. Inherit Phase 5/4 contracts and current `web/src/index.css`: existing light/dark teal/slate tokens, 4/8/16/24/32 spacing, 14px body/12px labels/20px headings/28px display, weights400/600, input height40px, coarse-pointer targets44px, bounded1280px layout and existing responsive breakpoints. No new color/font/npm dependency, no copied upstream appearance. UI/UX Pro Max's verified shadcn settings/Sheet guidance informed progressive disclosure; existing project components take precedence over introducing a new Accordion dependency.

## Scope

| Surface | Existing entry | New behavior | Owning plans |
|---|---|---|---|
| Chunking-method dialog | dataset files/settings | All fourteen documented methods, built-method availability, parser-specific settings and retained overrides | 03,07–14,15–19 |
| Parse configuration | existing chunk method form | Layout toggle, backend choice, page ranges, auto-keyword/question counts and optional enrichment settings | 03,04,21,22,26–29 |
| Chunk inspector/source drawer | existing document/chunk routes | Real OCR text, table HTML rendered safely, extracted images, slide/section labels, ASR timestamps, summary-to-leaf sources | 03–06,08–18,24 |
| Dataset tags | dataset workspace section | List, aggregate selected accessible datasets, delete confirmation, tag weights | 19,22 |
| Dataset/document metadata | dataset workspace/document selection | Flattened bounded scalar fields, schema/config display and batch edits with permission errors | 20,22 |
| Derived jobs/artifacts | dataset workspace section | RAPTOR enable/run, progress/cancel, result artifact download, scoped derived deletion and alteration history | 23–25 |
| Model settings | existing workspace model selectors | Configured vision/ASR/OCR types, missing-model action linking to existing provider settings | 15,16,27 |

No new global navigation family. Tags, metadata and derived-job sections remain inside the active dataset workspace. Use a right Sheet for supplementary inspector/history detail, existing Dialog for configuration and existing AlertDialog for destructive confirmations; never stack dialogs/sheets. No native service URL, model digest, container setting, internal sentinel ID or diagnostic counter belongs in a product form.

## Interaction contracts

`ParseConfiguration` currently renders layout/keywords as NotYetRows. Replace a row only with a working persisted control when its backend slice passes. Layout is a labelled checkbox/switch with helper text `Use layout analysis`; selecting a configured external backend preserves its explicit name and never silently falls back. Page ranges use human one-based inclusive values and existing parser-config validation. Method choice updates only parser_id and changed typed options; preserve unknown/hidden settings, existing document overrides and reparse confirmation.

All fourteen method names appear in the final dialog: General, Paper, Book, Laws, Presentation, Table, Q&A, Resume, Picture, Manual, Email, Tag, One chunk and Audio. Each has a one-sentence boundary description and supported-file helper. The card is keyboard selectable and an unavailable choice has a visible reason tied to its label; absence of an optional service does not select another method. Method catalog and provider capability data determine actual availability, not frontend hardcoding. Existing General defaults remain512 tokens, newline delimiter, zero overlap; advanced counts default0/off. Changing settings does not start a paid parse automatically.

Keyword count range0..32, question count0..16. Vision/OCR/ASR/summary selectors use configured workspace models and server-authorized composite IDs. Missing model: `Choose a {type} model in workspace settings.` An external backend that is unconfigured shows `This parser is not configured for this workspace.` No key field is duplicated into dataset settings. Enabling enrichment shows a concise cost helper `Parsing can use the selected model.` Counts/inputs remain bounded and labelled.

Tags show label plus weight, never color alone. Deletion confirmation names the dataset and exact derived effect; default focus is `Keep tags`, confirm is `Delete tags`. Metadata edits list selected document count, preserve unsent fields and show per-field refusals; no raw JSON HTML editor is required. Values render as text. Derived deletion names its allowed index type and states that original documents remain; use `Keep summaries` / `Delete summaries`. Do not expose arbitrary index_type strings as free text.

RAPTOR progress uses existing run/progress vocabulary and deadline polling; source chunks remain readable during generation. Cancelling marks the job honestly and does not publish an incomplete generation. A completed summary identifies its original source passages. Missing/deleted/unavailable leaves show existing unavailable-source copy and cannot be opened. A summary never opens a fictitious PDF page.

## Geometry, media and security

Source images load through authenticated blob requests, not token-bearing URLs. Decode/cache ownership is fenced by workspace/document/asset. Captions have descriptive alt text; timestamps are visible text and monotonic. Reserve page aspect ratio to avoid layout shifts, keep zoom controls keyboard accessible and retain PagePreview coordinate conversion. HTML tables are parsed/sanitized through the existing safe rendering path; no dangerouslySetInnerHTML for model output. Links are sanitized and no external resource in EPUB/email/Markdown is fetched automatically.

## States, copy and accessibility

Every new section has idle/loading/empty/error/ready states. Examples: `No tags yet.`, `No metadata yet.`, `No summaries yet.`, `Preparing document…`, `Parsing failed. Try again.`, `The parsing service is unavailable.` Fixed typed errors only, no provider exception text/path/host. Use existing Skeleton/EmptyState/ErrorState/Alert/sonner patterns. Per-field errors associate with inputs; failures preserve drafts and focus. Pending form submissions resist duplicates and retain a deliberate escape/close contract. Saving reports success only after server confirmation.

All query keys start `["ws", tenantId, …]`; wait for workspace binding, fence old requests on switch, include current dataset in request snapshots, invalidate in onSettled, retain previous paged data. No stale cross-workspace image, metadata, tag, summary or provider choice can flash. FE-01..04 and R-152 overlay rules remain unchanged. Touch targets40px/44px coarse, visible focus, reduced motion, contrast and screen-reader state announcements follow inherited rules.

Add English and draft Chinese strings to existing dataset/chunking/source/model areas, with plural forms and Intl formatting. New translation keys are tested. B-18 Chinese reader review remains human-only; automated parity does not mean wording approved.

## Review checklist (inline)

Six dimensions reviewed: scope covers every new user surface; inheritance avoids token drift; copy names actions/empty/failure states; accessibility covers focus/labels/touch/announcements; reuse introduces no package; implementation mapping links each surface to its feature plan and real API. Result: PASS for planning, no unresolved UI contract blocker. Human visual/copy approval is not claimed.

## Automated and human validation

Each owning plan includes Vitest behavioral checks and real-browser journeys when it changes UI behavior. Test local/delayed providers deterministically; paid vision/ASR/summary calls stay in the single Phase6 live budget. Final Chrome checks include scanned PDF->OCR chunks->cited answer/source, table/figure preview, method selection persistence, tags/metadata and summary deletion. Human checks judge exact OCR/read-order/table fidelity, word-level highlight alignment and Chinese copy. No automatic acceptance is inferred for those checks.
