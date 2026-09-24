from typing import List
from ..models import DocumentStructure, TextBlock
from .base import BaseChunker
from .models import Chunk, SourceRegion

class PresentationChunker(BaseChunker):
    def chunk(self, document: DocumentStructure) -> List[Chunk]:
        chunks = []
        chunk_idx = 0
        doc_id = document.document_id or ""
        
        for page in document.pages:
            slide_text = []
            for block in page.blocks:
                if isinstance(block, TextBlock):
                    slide_text.append(block.text.strip())
            
            if slide_text:
                chunks.append(Chunk(
                    text="\n".join(slide_text),
                    chunk_index=chunk_idx,
                    page_numbers=[page.page_number],
                    content_type="presentation",
                    metadata={"document_id": doc_id}
                ))
                chunk_idx += 1
                
        return chunks
