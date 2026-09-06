import re
from typing import List
from ..models import DocumentStructure, TextBlock, TableBlock
from .base import BaseChunker
from .models import Chunk, SourceRegion

class GeneralChunker(BaseChunker):
    def __init__(self, max_tokens: int = 500, min_tokens: int = 0, overlap_tokens: int = 0):
        super().__init__(max_tokens, min_tokens, overlap_tokens)
        
    def _split_into_sentences(self, text: str) -> List[str]:
        # Simple sentence boundary detection
        # Split on . ? ! followed by a space and an uppercase letter
        # This is a basic deterministic regex
        sentences = []
        start = 0
        for match in re.finditer(r'(?<=[.!?]) +(?=[A-Z0-9])', text):
            sentences.append(text[start:match.start()].strip())
            start = match.end()
        if start < len(text):
            sentences.append(text[start:].strip())
            
        return [s for s in sentences if s]
        
    def chunk(self, document: DocumentStructure) -> List[Chunk]:
        chunks = []
        chunk_idx = 0
        
        doc_id = document.document_id or ""
        
        current_text = ""
        current_tokens = 0
        current_pages = []
        current_regions = []
        current_block_ids = []
        
        def flush_buffer():
            nonlocal current_text, current_tokens, current_pages, current_regions, current_block_ids, chunk_idx
            if not current_text.strip():
                return
            
            # Create chunk
            chunks.append(Chunk(
                text=current_text.strip(),
                chunk_index=chunk_idx,
                page_numbers=sorted(list(set(current_pages))),
                source_regions=list(current_regions),
                source_block_ids=list(set(current_block_ids)),
                content_type="text",
                metadata={"document_id": doc_id}
            ))
            
            chunk_idx += 1
            current_text = ""
            current_tokens = 0
            current_pages = []
            current_regions = []
            current_block_ids = []
            
        for page in document.pages:
            for block in page.blocks:
                is_header_footer = False
                if isinstance(block, TextBlock):
                    if block.metadata.get("layout_type") in ["header", "footer"]:
                        # Skip decorative headers/footers in text chunks
                        continue
                        
                block_text = ""
                block_type = "text"
                
                if isinstance(block, TextBlock):
                    block_text = block.text
                elif isinstance(block, TableBlock):
                    # Process table
                    block_text = self._format_table(block)
                    block_type = "table"
                elif hasattr(block, "to_markdown"):
                    # TableStructure or similar
                    block_text = block.to_markdown()
                    block_type = "table"
                
                block_tokens = self.token_counter.count(block_text)
                
                # If block is a table, try to flush current text and output table as its own chunk
                if block_type == "table":
                    flush_buffer()
                    
                    if block_tokens <= self.max_tokens:
                        # Yield the whole table as a chunk
                        chunks.append(Chunk(
                            text=block_text.strip(),
                            chunk_index=chunk_idx,
                            page_numbers=[page.page_number],
                            source_regions=[SourceRegion(page=page.page_number, bbox=block.bbox)] if getattr(block, "bbox", None) else [],
                            source_block_ids=[block.block_id] if getattr(block, "block_id", None) else [],
                            content_type="table",
                            metadata={"document_id": doc_id}
                        ))
                        chunk_idx += 1
                    else:
                        # Large table fallback: split by rows if possible
                        # If it's markdown, split by newlines but keep header
                        lines = block_text.split("\n")
                        if len(lines) > 2 and "|" in lines[0] and "---" in lines[1]:
                            header = lines[0] + "\n" + lines[1]
                            header_tokens = self.token_counter.count(header)
                            
                            sub_text = header
                            sub_tokens = header_tokens
                            
                            for row in lines[2:]:
                                row_tokens = self.token_counter.count(row + "\n")
                                if sub_tokens + row_tokens > self.max_tokens and sub_tokens > header_tokens:
                                    chunks.append(Chunk(
                                        text=sub_text.strip(),
                                        chunk_index=chunk_idx,
                                        page_numbers=[page.page_number],
                                        source_regions=[SourceRegion(page=page.page_number, bbox=getattr(block, "bbox", None))] if getattr(block, "bbox", None) else [],
                                        source_block_ids=[block.block_id] if getattr(block, "block_id", None) else [],
                                        content_type="table",
                                        metadata={"document_id": doc_id}
                                    ))
                                    chunk_idx += 1
                                    sub_text = header + "\n" + row
                                    sub_tokens = header_tokens + row_tokens
                                else:
                                    sub_text += "\n" + row
                                    sub_tokens += row_tokens
                            
                            if sub_tokens > header_tokens:
                                chunks.append(Chunk(
                                    text=sub_text.strip(),
                                    chunk_index=chunk_idx,
                                    page_numbers=[page.page_number],
                                    source_regions=[SourceRegion(page=page.page_number, bbox=getattr(block, "bbox", None))] if getattr(block, "bbox", None) else [],
                                    source_block_ids=[block.block_id] if getattr(block, "block_id", None) else [],
                                    content_type="table",
                                    metadata={"document_id": doc_id}
                                ))
                                chunk_idx += 1
                        else:
                            # Not a standard table with headers, just yield it
                            chunks.append(Chunk(
                                text=block_text.strip(),
                                chunk_index=chunk_idx,
                                page_numbers=[page.page_number],
                                source_regions=[SourceRegion(page=page.page_number, bbox=getattr(block, "bbox", None))] if getattr(block, "bbox", None) else [],
                                source_block_ids=[block.block_id] if getattr(block, "block_id", None) else [],
                                content_type="table",
                                metadata={"document_id": doc_id}
                            ))
                            chunk_idx += 1
                    
                    continue # table is processed
                    
                # Text block logic
                if current_tokens + block_tokens <= self.max_tokens:
                    current_text += ("\n\n" if current_text else "") + block_text
                    current_tokens = self.token_counter.count(current_text)
                    current_pages.append(page.page_number)
                    if block.bbox:
                        current_regions.append(SourceRegion(page=page.page_number, bbox=block.bbox))
                    if getattr(block, "block_id", None):
                        current_block_ids.append(block.block_id)
                else:
                    # Does the block itself exceed max tokens?
                    if block_tokens > self.max_tokens:
                        # Flush current buffer
                        flush_buffer()
                        
                        # Split block by sentences
                        sentences = self._split_into_sentences(block_text)
                        for sentence in sentences:
                            s_tokens = self.token_counter.count(sentence)
                            if current_tokens + s_tokens > self.max_tokens:
                                if current_text:
                                    flush_buffer()
                                    
                                if s_tokens > self.max_tokens:
                                    # Fallback: oversized sentence, just chunk it raw
                                    # Split by words if needed, but the prompt says:
                                    # "if impossible, perform a safe token-based split"
                                    # Let's just output the sentence, or chunk it forcefully.
                                    # To simplify: output it as a single chunk even if oversized.
                                    # The prompt says: "never produce an infinite loop, preserve all source text"
                                    # We will split it by characters safely.
                                    words = sentence.split(" ")
                                    for w in words:
                                        w_tok = self.token_counter.count(w + " ")
                                        if current_tokens + w_tok > self.max_tokens and current_tokens > 0:
                                            flush_buffer()
                                        current_text += (" " if current_text else "") + w
                                        current_tokens = self.token_counter.count(current_text)
                                        current_pages.append(page.page_number)
                                        if block.bbox:
                                            current_regions.append(SourceRegion(page=page.page_number, bbox=block.bbox))
                                        if getattr(block, "block_id", None):
                                            current_block_ids.append(block.block_id)
                                    flush_buffer()
                                else:
                                    current_text = sentence
                                    current_tokens = s_tokens
                                    current_pages.append(page.page_number)
                                    if block.bbox:
                                        current_regions.append(SourceRegion(page=page.page_number, bbox=block.bbox))
                                    if getattr(block, "block_id", None):
                                        current_block_ids.append(block.block_id)
                            else:
                                current_text += (" " if current_text else "") + sentence
                                current_tokens = self.token_counter.count(current_text)
                                current_pages.append(page.page_number)
                                if block.bbox:
                                    current_regions.append(SourceRegion(page=page.page_number, bbox=block.bbox))
                                if getattr(block, "block_id", None):
                                    current_block_ids.append(block.block_id)
                        
                    else:
                        # Flush and start new chunk with this block
                        flush_buffer()
                        current_text = block_text
                        current_tokens = block_tokens
                        current_pages.append(page.page_number)
                        if block.bbox:
                            current_regions.append(SourceRegion(page=page.page_number, bbox=block.bbox))
                        if getattr(block, "block_id", None):
                            current_block_ids.append(block.block_id)
                            
        flush_buffer()
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
