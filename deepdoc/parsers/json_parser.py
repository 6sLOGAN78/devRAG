from pathlib import Path
import json

from .base import BaseParser
from ..models import DocumentStructure, TextBlock, PageNode
from ..errors import ParsingFailureError

class JsonParser(BaseParser):
    def parse(self, file_path: Path) -> DocumentStructure:
        self._validate_file(file_path)
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ParsingFailureError(f"Failed to read JSON file: {e}")

        blocks = []
        
        def traverse(obj, prefix=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    traverse(v, f"{prefix}.{k}" if prefix else str(k))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    traverse(v, f"{prefix}[{i}]")
            else:
                if obj is not None and str(obj).strip():
                    blocks.append(TextBlock(text=f"{prefix}: {str(obj).strip()}", block_id=prefix))

        traverse(data)
            
        page = PageNode(page_number=1, blocks=blocks)
        
        return DocumentStructure(
            source_path=str(file_path),
            file_type="json",
            pages=[page],
            metadata={}
        )
