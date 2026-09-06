from typing import Any, List
from pydantic import BaseModel, Field

class SourceRegion(BaseModel):
    page: int
    bbox: List[float] | None = None

class Chunk(BaseModel):
    id: str | None = None
    text: str
    chunk_index: int
    page_numbers: List[int] = Field(default_factory=list)
    source_regions: List[SourceRegion] = Field(default_factory=list)
    source_block_ids: List[str] = Field(default_factory=list)
    content_type: str = "text" # "text", "table", "qa"
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    @property
    def document_id(self) -> str | None:
        return self.metadata.get("document_id")

