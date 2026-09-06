import re
from typing import List
from ..models import DocumentStructure, TextBlock
from .base import BaseChunker
from .models import Chunk, SourceRegion

class QAChunker(BaseChunker):
    def __init__(self, max_tokens: int = 500, min_tokens: int = 0, overlap_tokens: int = 0):
        super().__init__(max_tokens, min_tokens, overlap_tokens)
        self.question_pattern = re.compile(r'^(?:Q|Question)[.:]\s*(.+)', re.IGNORECASE)
        self.answer_pattern = re.compile(r'^(?:A|Answer)[.:]\s*(.+)', re.IGNORECASE)
        
    def chunk(self, document: DocumentStructure) -> List[Chunk]:
        chunks = []
        chunk_idx = 0
        doc_id = document.document_id or ""
        
        current_q = None
        current_q_tokens = 0
        current_a = ""
        current_a_tokens = 0
        current_pages = []
        current_regions = []
        current_block_ids = []
        
        def flush_buffer():
            nonlocal current_q, current_a, current_q_tokens, current_a_tokens, current_pages, current_regions, current_block_ids, chunk_idx
            
            if not current_q and not current_a:
                return
                
            text = ""
            if current_q:
                text += current_q
            if current_a:
                text += ("\n" if text else "") + current_a
                
            text = text.strip()
            if not text:
                return
                
            # If Q+A exceeds max_tokens, we split the answer but repeat the question context
            if self.token_counter.count(text) > self.max_tokens and current_q and current_a:
                words = current_a.split(" ")
                sub_a = ""
                sub_tokens = current_q_tokens
                
                for w in words:
                    w_tok = self.token_counter.count(w + " ")
                    if sub_tokens + w_tok > self.max_tokens and sub_tokens > current_q_tokens:
                        chunks.append(Chunk(
                            text=f"{current_q}\n{sub_a.strip()}",
                            chunk_index=chunk_idx,
                            page_numbers=sorted(list(set(current_pages))),
                            source_regions=list(current_regions),
                            source_block_ids=list(set(current_block_ids)),
                            content_type="qa",
                            metadata={"document_id": doc_id}
                        ))
                        chunk_idx += 1
                        sub_a = w + " "
                        sub_tokens = current_q_tokens + w_tok
                    else:
                        sub_a += w + " "
                        sub_tokens += w_tok
                
                if sub_a.strip():
                    chunks.append(Chunk(
                        text=f"{current_q}\n{sub_a.strip()}",
                        chunk_index=chunk_idx,
                        page_numbers=sorted(list(set(current_pages))),
                        source_regions=list(current_regions),
                        source_block_ids=list(set(current_block_ids)),
                        content_type="qa",
                        metadata={"document_id": doc_id}
                    ))
                    chunk_idx += 1
            else:
                chunks.append(Chunk(
                    text=text,
                    chunk_index=chunk_idx,
                    page_numbers=sorted(list(set(current_pages))),
                    source_regions=list(current_regions),
                    source_block_ids=list(set(current_block_ids)),
                    content_type="qa" if current_q and current_a else "text",
                    metadata={"document_id": doc_id}
                ))
                chunk_idx += 1
                
            current_q = None
            current_q_tokens = 0
            current_a = ""
            current_a_tokens = 0
            current_pages = []
            current_regions = []
            current_block_ids = []

        for page in document.pages:
            for block in page.blocks:
                if not isinstance(block, TextBlock):
                    # For non-text blocks, just flush QA and ignore them or emit as text
                    # To keep simple, we'll flush
                    flush_buffer()
                    continue
                    
                text = block.text.strip()
                if not text:
                    continue
                    
                # Check for Q
                if self.question_pattern.match(text):
                    flush_buffer() # Flush previous QA pair
                    current_q = text
                    current_q_tokens = self.token_counter.count(current_q)
                    current_pages.append(page.page_number)
                    if block.bbox: current_regions.append(SourceRegion(page=page.page_number, bbox=block.bbox))
                    if block.block_id: current_block_ids.append(block.block_id)
                elif self.answer_pattern.match(text) and current_q:
                    # Append to answer
                    current_a += ("\n" if current_a else "") + text
                    current_a_tokens = self.token_counter.count(current_a)
                    current_pages.append(page.page_number)
                    if block.bbox: current_regions.append(SourceRegion(page=page.page_number, bbox=block.bbox))
                    if block.block_id: current_block_ids.append(block.block_id)
                elif current_q:
                    # Continuation of answer or question? Assume answer continuation
                    current_a += ("\n" if current_a else "") + text
                    current_a_tokens = self.token_counter.count(current_a)
                    current_pages.append(page.page_number)
                    if block.bbox: current_regions.append(SourceRegion(page=page.page_number, bbox=block.bbox))
                    if block.block_id: current_block_ids.append(block.block_id)
                else:
                    # Normal text, just accumulate or flush? 
                    # QA chunker handles QA patterns. Normal text is handled differently.
                    # We can just emit it.
                    flush_buffer()
                    current_q = text # Treat normal text as context or standalone
                    current_q_tokens = self.token_counter.count(current_q)
                    current_pages.append(page.page_number)
                    if block.bbox: current_regions.append(SourceRegion(page=page.page_number, bbox=block.bbox))
                    if block.block_id: current_block_ids.append(block.block_id)
                    flush_buffer()
                    
        flush_buffer()
        return chunks
