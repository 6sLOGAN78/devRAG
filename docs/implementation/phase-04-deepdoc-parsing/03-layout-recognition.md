## Objective
Implement layout recognition (using YOLOv8 or similar) to classify document regions (header, footer, paragraph, figure, table).

## Why Now?
To avoid naive chunking, the system must understand the visual structure of the page.

## Dependencies
- 02-ocr-engine

## Implementation Tasks
- [ ] Load pre-trained layout detection model (e.g., YOLO weights for DocLayNet).
- [ ] Create `LayoutRecognizer` class to run inference on page images.
- [ ] Filter out headers and footers from main content blocks.
- [ ] Correlate layout bounding boxes with OCR bounding boxes to assign text to logical sections.

## Components
- Layout Recognizer

## Files
- `deepdoc/vision/layout_recognizer.py`
- Weights stored in `assets/` or downloaded via script.

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
Page Image -> YOLO -> Layout Bounding Boxes -> Intersect with OCR -> Structured PageNode

## Testing
- Run on a multi-column PDF and verify reading order and block classification.

## Deliverable
Layout-aware parsing.

## Definition of Done
- Multi-column PDFs are read correctly without text bleeding across columns.

## Next Subphase
04-table-structure