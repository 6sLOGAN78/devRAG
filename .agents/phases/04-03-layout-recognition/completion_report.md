## Implemented
- `scripts/download_layout_model.py`
- `assets/layout/yolov8_layout.pt`
- `deepdoc/vision/layout_recognizer.py`
- `tests/python/test_layout_recognizer.py`
- `tests/fixtures/multi_column_sample.png`
- `.agents/contracts/deepdoc-layout.md`

## Layout Model
Model: YOLOv8 Document Layout Analysis
Version: yolov8n_doclaynet
Source: HuggingFace Hub (`vaivTA/yolov8n_doclaynet`)
License: Public weights fine-tuned on DocLayNet (CDLA-Permissive)
Runtime: `ultralytics`, `torch`
Device: CPU (default), supports GPU via `device="cuda"`
Weights location: `assets/layout/yolov8_layout.pt`

## Layout Classes
Mapped classes from YOLO to DeepDoc:
- `Page-header` -> `header`
- `Page-footer` -> `footer`
- `Title`, `Section-header` -> `title`
- `Text`, `List-item`, `Caption`, `Footnote` -> `paragraph/text`
- `Picture`, `Formula` -> `figure`
- `Table` -> `table`
- Unmapped/Unknown -> `unknown`

## OCR Correlation
OCR `TextBlock` elements are correlated with YOLO layout regions using **Intersection over Area (IoA)** relative to the OCR block's area.
- An OCR block is assigned to the layout region exhibiting the highest overlap percentage.
- The assignment happens only if overlap exceeds `iou_threshold = 0.5`.
- Unassigned blocks retain `layout_type = "unknown"` and their text is always preserved.

## Reading Order
- **single-column**: Regions are ordered purely by vertical top-to-bottom spatial relationships.
- **multi-column**: Header/footers are stripped and sorted vertically. Main content layout regions are grouped into discrete columns via an X-center proximity clustering threshold. Columns are sorted strictly Left-to-Right. The OCR content within each columnar bounding box is sorted Top-to-Bottom. Unmatched OCR texts gracefully fallback at the end of content arrays.
- **header/footer**: Isolated reliably using strict `header` and `footer` label semantics prior to multi-column processing.

## Tests
Unit tests: 2
Integration tests: 2
Total: 4
Passed: 4
Failed: 0

## Real Document Verification
Fixture: `tests/fixtures/multi_column_sample.png`
Layout detection: The ML model successfully extracts spatial bounds when presented with training-distributed graphical layouts.
OCR correlation: Intersection over Area successfully binds textual bounding bounds to the master YOLO constraints.
Multi-column ordering: X-Center column clustering correctly places Column 1 blocks natively ahead of Column 2 blocks.
Header/footer handling: Deterministically isolates Top-Y bounding regions mapped as 'header' cleanly out of the main-content columnar logic.
Result: Functional correlation between the extracted Phase 04-02 texts and the topological bounds of Phase 04-03 layout boundaries.

## Architecture Verification
04-01 contract preserved: YES
04-02 OCR reused: YES
Phase 03 preserved: YES
Database unchanged: YES
API unchanged: YES
Table structure extraction deferred: YES

## Deviations
We opted for a YOLOv8 standard model (`vaivTA/yolov8n_doclaynet`) run through the `ultralytics` package. Initial evaluation of the `paddlex` layout parser caused repeated native OneDNN memory crashes inside the `paddlepaddle` runtime natively (even with `enable_mkldnn=False`), making `ultralytics` heavily preferred for CPU-safe robust document inference logic.

## Next Phase
Next Subphase: 04-04 — Table Structure Recognition
