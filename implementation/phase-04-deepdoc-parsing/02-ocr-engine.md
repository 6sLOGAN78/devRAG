## Objective
Integrate PaddleOCR (or similar) to extract text from images and scanned PDF pages.

## Why Now?
OCR is a fundamental primitive for vision-based parsing.

## Dependencies
- 01-deepdoc-interfaces

## Implementation Tasks
- [ ] Add PaddleOCR to `requirements.txt`.
- [ ] Create `OcrEngine` wrapper class.
- [ ] Implement image preprocessing (deskew, binarization) if necessary.
- [ ] Map OCR output to `TextBlock` bounding boxes.

## Components
- OCR Engine Wrapper

## Files
- `deepdoc/vision/ocr.py`

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
Image Path -> OcrEngine -> List[TextBlock]

## Testing
- Unit test with a sample scanned image to verify text extraction accuracy.

## Deliverable
Working OCR pipeline.

## Definition of Done
- Scanned text can be reliably extracted into bounding boxes.

## Next Subphase
03-layout-recognition