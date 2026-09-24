from typing import List
from ..models import DocumentStructure, TextBlock, TableBlock
from .base import BaseChunker
from .models import Chunk, SourceRegion

class TableChunker(BaseChunker):
    def chunk(self, document: DocumentStructure) -> List[Chunk]:
        chunks = []
        chunk_idx = 0
        doc_id = document.document_id or ""
        
        for page in document.pages:
            for block in page.blocks:
                if isinstance(block, TableBlock):
                    # Convert TableBlock to Markdown
                    md_rows = []
                    for r_idx, row in enumerate(block.rows):
                        clean_row = [str(c).replace("\n", " ") for c in row]
                        md_rows.append("| " + " | ".join(clean_row) + " |")
                        if r_idx == 0:
                            md_rows.append("| " + " | ".join(["---"] * block.columns) + " |")
                    
                    text = "\n".join(md_rows)
                    chunks.append(Chunk(
                        text=text,
                        chunk_index=chunk_idx,
                        page_numbers=[page.page_number],
                        content_type="table",
                        metadata={"document_id": doc_id}
                    ))
                    chunk_idx += 1
                elif isinstance(block, TextBlock):
                    # Fallback for text
                    chunks.append(Chunk(
                        text=block.text,
                        chunk_index=chunk_idx,
                        page_numbers=[page.page_number],
                        content_type="text",
                        metadata={"document_id": doc_id}
                    ))
                    chunk_idx += 1
                    
        return chunks
