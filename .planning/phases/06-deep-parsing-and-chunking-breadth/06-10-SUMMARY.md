---
phase: 06-deep-parsing-and-chunking-breadth
plan: "10"
subsystem: epub-and-book
requirements-completed: []
---

# Plan06-10: Read EPUB books in chapter order

EPUB now reads the container and OPF manifest in declared spine order, with EPUB3 navigation or EPUB2 NCX ancestry. The original fixture deliberately stores orchard before lighthouse in ZIP order; parsing and retrieval retain lighthouse first. Bounded archive checks reject duplicate members, traversal, symlinks, encrypted members, expansion bombs, malformed XML, DTD/entities, excessive XML depth/nodes, missing or repeated spine IDs/targets and remote manifest addresses. Files are never extracted and resources never fetched. Existing inert HTML extraction is shared and now retains heading levels; XML namespaces are explicit. Empty content refuses. No new package/model is needed.

Book owns its config and chunker, keeps chapters/sections separate, repeats ancestry on long prose chunks and preserves source geometry, line ranges, typed tables and image IDs. Defaulted typed Section metadata records chapter paths and source archive paths; conditional index fields preserve these without fabricated pages. Non-EPUB heading-based documents work too. The actual embedding model context is checked before encode. The existing dialog saves Book and explains supported formats and chapter order, keeps size usable and disables ignored delimiter/overlap controls. Static Go catalog, Python and frontend availability agree.

Validation: full Python2605passed/8existing skips; frontend2163passed107files; Go internal green. Real worker2pass including deterministic retry IDs, Chrome1pass with assistant-inspected source screenshot, native/parser/browser regressions36pass, services84pass, routes166pass and leaks6pass. CI7/security/generated/OpenAPI/admission green. App/worker/native were rebuilt and healthy before browser verification using the unchanged matching-manifest approved runtime. Zero paid calls. See06-10-VERIFICATION.json for log hashes and image identities.

Review and deviations: self-review inline (agents not authorized). Separate bounded epub_archive.py/sections.py keep trust checks and evidence types cohesive. Hardening caught duplicate physical spine paths under different IDs (RED→GREEN). Malformed integration fixture was corrected to pass upload magic and reach the intended parser refusal. Legacy test-only assumptions were updated: unavailable QA/Book fixtures now use still-unbuilt methods; exact Go public catalog routes are exceptions to family JWT defaults in the Python-only enumeration check. Two chat rail tests now wait for committed selection/initial composer focus before testing selection/pagination; original assertions and timeouts remain. Complete supplemental glue and reasons are in06-10-PROGRESS.md and06-10-FILES.txt.

R-241 is accepted automatically, not user-reviewed. REQUIREMENTS.md is unchanged. Phase5 final human acceptance, Phase4 B36 and full Phase6 gate/UAT remain pending. Next plan11 delivers Paper section structure.
