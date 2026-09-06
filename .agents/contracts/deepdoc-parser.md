# DeepDoc Parser Contract

## Purpose
DeepDoc provides the Python document-processing infrastructure for devRAG. It is responsible for transforming raw input files into a normalized internal data structure (`DocumentStructure`).

DeepDoc is strictly a text/data extraction abstraction and is **not** responsible for:
- Authentication
- Tenant authorization
- Database CRUD operations
- Object storage operations
- Chunking, embedding, or retrieval logic

## Core Models

### DocumentStructure
The root model representing a parsed file.
```python
class DocumentStructure(BaseModel):
    document_id: str | None = None
    source_path: str | None = None
    file_type: str | None = None
    pages: list[PageNode]
    metadata: dict[str, Any]
```

### PageNode
Represents a logical page or pagination boundary within a document.
```python
class PageNode(BaseModel):
    page_number: int
    blocks: list[TextBlock | TableBlock]
    metadata: dict[str, Any]
```

### TextBlock
Represents extracted textual content.
```python
class TextBlock(BaseModel):
    text: str
    block_id: str | None = None
    bbox: list[float] | None = None
    style: dict[str, Any] | None = None
    metadata: dict[str, Any]
```

### TableBlock
Represents extracted tabular information.
```python
class TableBlock(BaseModel):
    rows: list[list[str]]
    columns: int | None = None
    block_id: str | None = None
    bbox: list[float] | None = None
    metadata: dict[str, Any]
```

## Parser Interface
The core parser abstraction requires every parser to implement the `parse` method, transforming a file path into a `DocumentStructure`.
```python
class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: Path) -> DocumentStructure:
        pass
```

## Current Parsers
- `TxtParser`: Extracts plain text as simple paragraphs and groups them into a single `PageNode`.
- `MarkdownParser`: Extracts text and lightweight logical blocks (headings, paragraphs) mapped to styles within `TextBlock` objects inside a single `PageNode`.

## Error Contract
Parsers must throw explicit subclasses of `ParserError` to indicate failure modes rather than bubbling raw library exceptions to consumers:
- `InvalidInputError`: Raised when the input file is non-existent, unreadable, or invalid.
- `UnsupportedFormatError`: Raised when the parser does not handle the given format.
- `ParsingFailureError`: Raised for internal errors or corrupt file data encountered during parsing.

## Extension Model
DeepDoc is designed to be easily extensible. New formats can be supported by subclassing `BaseParser` without modifying upstream consumers.
```text
BaseParser
    ├── TxtParser (Implemented)
    ├── MarkdownParser (Implemented)
    ├── PdfParser (Future Phase)
    ├── OCRParser (Future Phase)
    └── DocxParser (Future Phase)
```

## Architectural Boundary
The Python DeepDoc engine is completely disjoint from the Go web layers managing SQL CRUD boundaries (`Dataset`, `Document`). 
Future integration phases will pass raw MinIO file streams to these Python parsers, allowing the outputs to be fed sequentially into chunking and embedding nodes independently of database schemas.
