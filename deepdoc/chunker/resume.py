from typing import List
from ..models import DocumentStructure, TextBlock
from .base import BaseChunker
from .models import Chunk, SourceRegion

class ResumeChunker(BaseChunker):
    def chunk(self, document: DocumentStructure) -> List[Chunk]:
        chunks = []
        chunk_idx = 0
        doc_id = document.document_id or ""
        
        # Resume chunker tries to keep large continuous blocks together
        # and flags them as 'resume' content type for specialized retrieval.
        current_text = ""
        current_pages = []
        
        for page in document.pages:
            for block in page.blocks:
                if isinstance(block, TextBlock):
                    text = block.text.strip()
                    if not text: continue
                    
                    if self.token_counter.count(current_text + "\n" + text) > self.max_tokens:
                        chunks.append(Chunk(
                            text=current_text.strip(),
                            chunk_index=chunk_idx,
                            page_numbers=sorted(list(set(current_pages))),
                            content_type="resume",
                            metadata={"document_id": doc_id}
                        ))
                        chunk_idx += 1
                        current_text = text
                        current_pages = [page.page_number]
                    else:
                        current_text += ("\n" if current_text else "") + text
                        current_pages.append(page.page_number)
                        
        if current_text:
            chunks.append(Chunk(
                text=current_text.strip(),
                chunk_index=chunk_idx,
                page_numbers=sorted(list(set(current_pages))),
                content_type="resume",
                metadata={"document_id": doc_id}
            ))
            
        return chunks
