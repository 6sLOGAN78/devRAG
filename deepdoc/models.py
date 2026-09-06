from typing import Any

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    text: str
    block_id: str | None = None
    bbox: list[float] | None = None
    style: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class TableBlock(BaseModel):
    rows: list[list[str]]
    columns: int | None = None
    block_id: str | None = None
    bbox: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class PageNode(BaseModel):
    page_number: int
    blocks: list[TextBlock | TableBlock] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

class DocumentStructure(BaseModel):
    document_id: str | None = None
    source_path: str | None = None
    file_type: str | None = None
    pages: list[PageNode] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
