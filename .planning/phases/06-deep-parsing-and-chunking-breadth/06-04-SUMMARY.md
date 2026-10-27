---
phase: 06-deep-parsing-and-chunking-breadth
plan: "04"
subsystem: native-layout
requirements-completed: []
---

# Plan 06-04: Preserve visual reading order and remove page furniture

The approved local layout.onnx now runs in the isolated CPU service before readiness is advertised. Byte-only authenticated /v1/layout and PDF layout options share the bounded native executor and existing timeout/slot retention. No runtime acquisition, URL input or changed dependency/model acceptance. The ten artifact classes map explicitly to the documented eleven canonical semantic IDs. Score0.08 is compared in the model's float32 representation; class-aware deterministic NMS uses IoU0.45; text-region matching uses intersection/text-box area>=0.4. Unknown labels/nonfinite results refuse. Typed defaulted layout labels preserve heading/table/figure/reference semantics without fabricating assets before05.

Layout-on retains native rectangles until model matching and stable column order; layout-off retains original native grouping. Header/Footer are removed and Reference is preserved. For ambiguous model “abandon” detections, margin interpretation requires independent interior body evidence; the unchanged short NATIVE FACT page remains readable. Iterative reading-order traversal handles1100wide headings without recursion failure. Crop/rotation/letterbox transforms return the existing one-based, top-left page units exactly once.

The original fixed two-column PDF returns ALPHA→BRAVO→CHARLIE→DELTA with both planted furniture strings absent. Actual Chrome toggles off, parses interleaved text/furniture, saves/reopens on, reparses into correct order and shows the real source boxes. Original furniture remains visible only in the source image. Backend/region evidence reaches operation DSL while machine lines stay out of user-facing progress. Existing form/document/dataset DTOs preserve unrelated/named backend settings. Unsupported named backends refuse rather than falling back; their actual implementations belong to later plans.

Verification: final native/API/Chrome/legacy21passed139.87s, unit2500passed/8existing skips, web2141passed105files plus36focused preservation checks, production build and CI7/7/security/async gates pass. Mixed native/scanned source facts and corrupted native-text ratio decisions are covered in the actual native container; host NumPy remains absent. Final five-repeat cold offline guard all qualitypass: p50/page2.6261s,p95/page2.7948s,peakRSS561.848MiB,load0.847s under2CPU/3GiB/read-only/networknone. See06-04-LAYOUT-GUARD.json for every raw sample and image identity. The3GiB trial cap remains for broader table/audio workloads; this tiny corpus is not production capacity proof.

## Deviations and review

[Rule1] Native grouping fused columns before layout; fixed unmerged extraction for layout-on, preserving off behavior. [Rule1] Float32 score boundary dropped a detection at0.08; exact native-container threshold/letterbox RED→GREEN. [Rule1] Ambiguous Header/Text overlap removed the short source; preserved failure/regions and required independent body evidence, without retuning the fixed fixture or thresholds. [Rule1] Many headings exhausted recursion; explicit work-stack traversal passes the original1100-heading regression. [Rule3] Native image explicitly copies shared parser types instead of depending on stale app source. Initial host-NumPy test setup failure was rejected as RED and moved into the isolated native container. Two busy503 failures were contaminated by my overlapping ad-hoc probes; the clean reruns passed without weakening concurrency or assertions. Guard checks use explicit exits, satisfying the security lint without disabling checks.

Inline self-review used actual runtime/UI evidence and the fixed boundary tests; no authorized subagent request existed. No unresolved correctness finding, paid request, requirement checkbox change or human UAT approval is claimed. Actual artifact license-label decision is unchanged. Complete file manifest:06-04-FILES.txt. Shared03 closeout and R234/R235 are recorded;05 is next.
