from pathlib import Path
from bs4 import BeautifulSoup

from .base import BaseParser
from ..models import DocumentStructure, TextBlock, PageNode
from ..errors import ParsingFailureError

class HtmlParser(BaseParser):
    def parse(self, file_path: Path) -> DocumentStructure:
        self._validate_file(file_path)
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                html_content = f.read()
        except Exception as e:
            raise ParsingFailureError(f"Failed to read HTML file: {e}")

        soup = BeautifulSoup(html_content, "html.parser")
        
        # Remove scripts and styles
        for element in soup(["script", "style"]):
            element.decompose()
            
        text = soup.get_text(separator="\n\n")
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        
        blocks = []
        for idx, p in enumerate(paragraphs):
            blocks.append(TextBlock(text=p, block_id=str(idx)))
            
        page = PageNode(page_number=1, blocks=blocks)
        
        return DocumentStructure(
            source_path=str(file_path),
            file_type="html",
            pages=[page],
            metadata={"title": soup.title.string if soup.title else None}
        )
