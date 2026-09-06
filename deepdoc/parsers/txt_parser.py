from pathlib import Path

from ..errors import ParsingFailureError
from ..models import DocumentStructure, PageNode, TextBlock
from .base import BaseParser


class TxtParser(BaseParser):
    """Parser for plain text (.txt) files."""
    
    def parse(self, file_path: Path) -> DocumentStructure:
        self._validate_file(file_path)
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                # Fallback for some common encodings if needed
                with open(file_path, "r", encoding="latin-1") as f:
                    content = f.read()
            except Exception as e:
                raise ParsingFailureError(f"Failed to read file due to encoding issues: {e}")
        except Exception as e:
            raise ParsingFailureError(f"Failed to read text file: {e}")

        # Split into simple logical paragraphs for text blocks
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        
        blocks = []
        for idx, p in enumerate(paragraphs):
            blocks.append(TextBlock(text=p, block_id=str(idx)))
            
        # Treat the entire TXT as a single logical page
        page = PageNode(page_number=1, blocks=blocks)
        
        return DocumentStructure(
            source_path=str(file_path),
            file_type="txt",
            pages=[page],
            metadata={"total_blocks": len(blocks)}
        )
