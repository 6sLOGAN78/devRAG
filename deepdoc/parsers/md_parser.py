import re
from pathlib import Path

from ..errors import ParsingFailureError
from ..models import DocumentStructure, PageNode, TextBlock
from .base import BaseParser


class MarkdownParser(BaseParser):
    """Parser for Markdown (.md) files."""
    
    def parse(self, file_path: Path) -> DocumentStructure:
        self._validate_file(file_path)
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            raise ParsingFailureError(f"Failed to read markdown file: {e}")

        # Split into blocks based on double newlines
        raw_blocks = [p.strip() for p in content.split("\n\n") if p.strip()]
        
        blocks = []
        for idx, block_text in enumerate(raw_blocks):
            # Check if it's a heading
            heading_match = re.match(r'^(#{1,6})\s+(.*)$', block_text)
            style = None
            if heading_match:
                level = len(heading_match.group(1))
                style = {"type": "heading", "level": level}
            else:
                style = {"type": "paragraph"}
                
            blocks.append(TextBlock(
                text=block_text, 
                block_id=str(idx),
                style=style
            ))
            
        # Treat the entire Markdown as a single logical page
        page = PageNode(page_number=1, blocks=blocks)
        
        return DocumentStructure(
            source_path=str(file_path),
            file_type="markdown",
            pages=[page],
            metadata={"total_blocks": len(blocks)}
        )
