## Objective
Define the base interfaces and data models for document parsing results.

## Why Now?
We need a standard schema for what a "Parsed Document Chunk" looks like before implementing the models.

## Dependencies
- Phase 03

## Implementation Tasks
- [ ] Define Python Pydantic models for `DocumentStructure`, `PageNode`, `TextBlock`, `TableBlock`.
- [ ] Define abstract `BaseParser` class with `parse(file_path)` method.
- [ ] Create stub parsers for TXT and Markdown (simple baseline).

## Components
- DeepDoc Core Models

## Files
- `deepdoc/models.py`
- `deepdoc/parsers/base.py`
- `deepdoc/parsers/txt_parser.py`

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
N/A

## Testing
- Unit test TXT parser.

## Deliverable
DeepDoc interface contract.

## Definition of Done
- Standardized chunk schema exists.

## Next Subphase
02-ocr-engine