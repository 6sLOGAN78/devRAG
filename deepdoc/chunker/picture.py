from typing import List
from ..models import DocumentStructure, TextBlock
from .base import BaseChunker
from .models import Chunk, SourceRegion

class PictureChunker(BaseChunker):
    def chunk(self, document: DocumentStructure) -> List[Chunk]:
        chunks = []
        chunk_idx = 0
        doc_id = document.document_id or ""
        
        # Simple picture chunker, picture texts usually come from OCR 
        for page in document.pages:
            for block in page.blocks:
                if isinstance(block, TextBlock):
                    chunks.append(Chunk(
                        text=block.text.strip(),
                        chunk_index=chunk_idx,
                        page_numbers=[page.page_number],
                        content_type="picture",
                        metadata={"document_id": doc_id}
                    ))
                    chunk_idx += 1
                    
        return chunks
