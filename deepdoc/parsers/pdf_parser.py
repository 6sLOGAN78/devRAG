from pathlib import Path
import pdfplumber

from .base import BaseParser
from ..models import DocumentStructure, TextBlock, PageNode
from ..errors import ParsingFailureError

class PdfParser(BaseParser):
    def parse(self, file_path: Path) -> DocumentStructure:
        self._validate_file(file_path)
        pages = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    blocks = []
                    if text:
                        # Split by paragraphs minimally
                        paragraphs = text.split('\n\n')
                        for p in paragraphs:
                            p = p.strip()
                            if p:
                                blocks.append(TextBlock(
                                    text=p,
                                    page_numbers=[i + 1]
                                ))
                    
                    pages.append(PageNode(
                        page_number=i+1,
                        width=page.width,
                        height=page.height,
                        blocks=blocks
                    ))
        except Exception as e:
            raise ParsingFailureError(f"Failed to parse PDF: {e}")
            
        return DocumentStructure(
            pages=pages
        )
