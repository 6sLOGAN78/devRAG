from typing import List, Union
from ..models import DocumentStructure, TextBlock, TableBlock
from .base import BaseChunker
from .models import Chunk, SourceRegion

class ManualChunker(BaseChunker):
    def __init__(self, max_tokens: int = 500, min_tokens: int = 0, overlap_tokens: int = 0):
        super().__init__(max_tokens, min_tokens, overlap_tokens)

    def chunk(self, document: DocumentStructure) -> List[Chunk]:
        """
        By default, ManualChunker treats every individual block as its own chunk, 
        expecting the caller to have structured the document blocks exactly as desired.
        """
        chunks = []
        chunk_idx = 0
        doc_id = document.document_id or ""
        
        for page in document.pages:
            for block in page.blocks:
                if isinstance(block, TextBlock):
                    text = block.text
                elif isinstance(block, TableBlock) or hasattr(block, "to_markdown"):
                    text = block.to_markdown() if hasattr(block, "to_markdown") else self._format_table(block)
                else:
                    text = str(block)
                    
                if not text.strip():
                    continue
                    
                chunks.append(Chunk(
                    text=text.strip(),
                    chunk_index=chunk_idx,
                    page_numbers=[page.page_number],
                    source_regions=[SourceRegion(page=page.page_number, bbox=block.bbox)] if getattr(block, "bbox", None) else [],
                    source_block_ids=[block.block_id] if getattr(block, "block_id", None) else [],
                    content_type="table" if isinstance(block, TableBlock) or hasattr(block, "to_markdown") else "text",
                    metadata={"document_id": doc_id}
                ))
                chunk_idx += 1
                
        return chunks
        
    def chunk_blocks(self, grouped_blocks: List[List[Union[TextBlock, TableBlock]]], document_id: str = "") -> List[Chunk]:
        """
        Explicitly chunk grouped blocks provided by the caller.
        """
        chunks = []
        for i, group in enumerate(grouped_blocks):
            if not group:
                continue
                
            text = ""
            pages = []
            regions = []
            block_ids = []
            c_type = "text"
            
            for block in group:
                if isinstance(block, TextBlock):
                    text += ("\n\n" if text else "") + block.text
                elif isinstance(block, TableBlock) or hasattr(block, "to_markdown"):
                    text += ("\n\n" if text else "") + (block.to_markdown() if hasattr(block, "to_markdown") else self._format_table(block))
                    c_type = "table"
                
                # We can't cleanly extract page from standalone block unless it has metadata, but assume caller knows
                page_num = block.metadata.get("page_number", 1) if getattr(block, "metadata", None) else 1
                pages.append(page_num)
                if getattr(block, "bbox", None):
                    regions.append(SourceRegion(page=page_num, bbox=block.bbox))
                if getattr(block, "block_id", None):
                    block_ids.append(block.block_id)
                    
            if text.strip():
                chunks.append(Chunk(
                    text=text.strip(),
                    chunk_index=i,
                    page_numbers=sorted(list(set(pages))),
                    source_regions=regions,
                    source_block_ids=list(set(block_ids)),
                    content_type=c_type,
                    metadata={"document_id": document_id}
                ))
                
        return chunks

    def _format_table(self, block: TableBlock) -> str:
        if not block.rows:
            return ""
        cols = block.columns or max(len(r) for r in block.rows)
        md = []
        for i, row in enumerate(block.rows):
            md.append("| " + " | ".join(row + [""] * (cols - len(row))) + " |")
            if i == 0:
                md.append("|" + "|".join(["---"] * cols) + "|")
        return "\n".join(md)
