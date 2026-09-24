# Deep Document Parsing & Vision (`/deepdoc`)

The `deepdoc` module provides DevRAG with enterprise-grade document extraction capabilities. It processes raw unstructured files into structured Pydantic models (`DocumentStructure`, `PageNode`, `TextBlock`, `TableBlock`) for downstream RAG chunking.

## Capabilities

### Parsers (`/parsers`)
Native file extractors that handle layout mapping.
- **Office/Text**: `DOCX`, `PPTX`, `XLSX`, `PDF`, `TXT`, `MD`, `HTML`, `JSON`.
- **Image/Vision**: `JPG`, `PNG` (OCR execution).

### Chunkers (`/chunker`)
Specialized segmentation algorithms for generating optimized vector chunks.
- **QA**: Generates Question & Answer pairs.
- **Resume**: Specialized continuity for CVs.
- **Table**: Markdown-aware matrix extractions.
- **Laws/Paper/Presentation**: Structure-aware parsing strategies.

### Vision Engine (`/vision`)
- **OCR Engine**: Powered by `PaddleOCR` (or ONNX endpoints) for text extraction from unstructured images and scanned PDFs.
- **Layout Recognition**: YOLO-based parsing for determining reading order and detecting figures, titles, and headers.
