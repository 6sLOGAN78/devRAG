## Objective
Implement Table Structure Recognition (TSR) to reconstruct visual tables into Markdown or HTML formats.

## Why Now?
Tables hold critical enterprise data and are destroyed by standard parsers.

## Dependencies
- 03-layout-recognition

## Implementation Tasks
- [ ] Implement TSR model integration.
- [ ] Extract grid structures and merge cells based on bounding box alignment.
- [ ] Map OCR text into table cells.
- [ ] Output table as Markdown/HTML string.

## Components
- Table Structure Recognizer

## Files
- `deepdoc/vision/table_structure_recognizer.py`

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
Table Image Box -> TSR Model -> Grid -> OCR Cells -> Markdown Table

## Testing
- Test with a complex financial balance sheet PDF.

## Deliverable
Accurate table extraction.

## Definition of Done
- Visual tables are converted to accurate Markdown representations.

## Next Subphase
05-chunking-strategies