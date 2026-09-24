from pathlib import Path
from .base import BaseParser
from ..models import DocumentStructure, PageNode
from ..errors import ParsingFailureError
from ..vision.ocr import get_ocr_engine

class ImageParser(BaseParser):
    def __init__(self, use_gpu: bool = False):
        self.ocr_engine = get_ocr_engine(use_gpu=use_gpu)

    def parse(self, file_path: Path) -> DocumentStructure:
        self._validate_file(file_path)
        
        try:
            blocks = self.ocr_engine.extract(file_path)
        except Exception as e:
            raise ParsingFailureError(f"Failed to OCR image: {e}")
            
        page = PageNode(page_number=1, blocks=blocks)
        
        return DocumentStructure(
            source_path=str(file_path),
            file_type="image",
            pages=[page],
            metadata={"total_blocks": len(blocks)}
        )
