---
phase: 06-deep-parsing-and-chunking-breadth
plan: "07"
subsystem: whole-document-and-static-catalog
requirements-completed: []
---

# Plan06-07: Choose whole-document chunks and inspect public pipeline templates

One document now emits exactly one chunk with every selected source position, page size, structured table and opaque owned image ID. Its method-specific configuration ignores General's split budget. Empty text produces no fabricated chunk; content beyond the embedding driver ceiling refuses with terminal chunk_too_long. The actual model's input limit is checked again before encode so the provider cannot silently truncate the document. Fixed English/Chinese copy offers another method; no provider request occurs on oversized input.

The scheduler creates one task for One, including PDFs longer than the twelve-page batch and disjoint selected ranges. The worker merges/intersects selections, parses them in source order, polls cancellation between calls, aggregates selected-page reports and bounds combined text/assets. The original source page count remains separate. A real14-page PDF selection2–3,13–14 produces one task/one chunk, exact original page numbers, four selected report pages and fourteen source pages. A second actual PDF preserves both TSR tables, authenticated crop IDs and identical indexed image references in one chunk. No native fallback or model change.

The Go binary now embeds a finite14-template catalog. List with type=builtin and detail return only id/name/description/parser_id/parser_config/available; availability honestly includes naive/one and is checked against the Python factory. Returned copies cannot mutate embedded data. Unknown/duplicate types and unknown IDs have fixed responses without reflection. The exact two public GET policies override protected Go routing families; other methods and deeper paths remain default-deny. Actual Nginx responses are Go-owned and byte-identical with absent, valid and invalid credentials. No DB/config/tenant lookup, Python controller or canvas runtime was added. The combined API schema describes these Go routes and generated Nginx/Vite/policy/OpenAPI/TypeScript agree. PARSE-26/CHUNK-28 Go runtime mirrors remain deferred by the existing decision.

The existing chunk-method dialog now lists all14 documented choices, enables One only after its implementation, saves/reopens it and keeps workspace/common page/layout behavior. Nonapplicable split settings stay visible with explanatory copy. Chrome successfully saved One and the assistant inspected the screenshot. This is not user UAT approval.

Verification: full root unit2541passed/8existing skips, frontend2158passed107files, all Go internal packages pass, affected real services104passed, native03/04/05/06 plus table Chrome20passed, route ownership/OpenAPI70passed, actual response/log leaks6passed, CI7/7/security/generated/admission pass. Final freshly rebuilt images passed all five new real integration/browser checks after formatting-only cleanup; focused unit12passed. The same original sources and assertions remain unchanged. See06-07-VERIFICATION.json,06-07-RUNTIME.json and complete06-07-FILES.txt.

## Deviations and review

Supplemental glue was declared in06-07-PROGRESS before edits: scheduling/selected-report aggregation, defaulted image-ID contracts/index metadata, pre-provider context failure, finite catalog metadata/parity, explicit public registry exceptions and combined schema. Existing explicit eight-method/one-built-method snapshots and the frontend test-server availability were updated to the actual build; public family default-deny tests now resolve exact GET overrides and still assert protected POSTs. Setup mistakes in helper request shapes/schema extension lookup and raw TXT blank separators were corrected without production stubs or weakened facts.

A standard native rebuild began re-downloading unchanged approved wheels after the app base changed and stalled. Only that build was interrupted. The recorded one-off06-07-NATIVE-REBUILD.Dockerfile copied the exact already-verified native vendor cache from the existing plan06 image into the fresh app base, then copied all current native/parser source. Final rebuild reused that same vendor chain. No new image from an external source, package/model version or acquisition occurred; the standard product Dockerfile remains unchanged. Final images and all relevant native paths were exercised.

R-238 is accepted automatically, not user-reviewed. No REQUIREMENTS.md checkbox or full-phase completion claim. Next08 adds bounded Markdown structure and Manual chunking. Phase5 final human acceptance and Phase4 B36 remain separate/pending; Phase6 gate/user UAT remain pending.

The final-image retry initially hit MinIO XMinioStorageFull. User explicitly approved unused/unshared build-cache cleanup and continuation. Exact cache IDs were verified reclaimable/unshared;13.48GB reclaimed with Docker image/container/network/volume inventories unchanged. Storage write/delete probe and final five checks passed afterward. See06-07-STORAGE-BLOCKER.json. This same cache-only policy is approved as needed during Phase6; no broader resource deletion is authorized.
