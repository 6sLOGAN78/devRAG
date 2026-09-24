from pathlib import Path
import openpyxl

from .base import BaseParser
from ..models import DocumentStructure, TableBlock, PageNode
from ..errors import ParsingFailureError

class ExcelParser(BaseParser):
    def parse(self, file_path: Path) -> DocumentStructure:
        self._validate_file(file_path)
        
        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
        except Exception as e:
            raise ParsingFailureError(f"Failed to read Excel file: {e}")

        pages = []
        for i, sheet_name in enumerate(wb.sheetnames):
            sheet = wb[sheet_name]
            rows_data = []
            max_cols = 0
            for row in sheet.iter_rows(values_only=True):
                # Convert all values to string, handling None
                row_text = [str(cell).strip() if cell is not None else "" for cell in row]
                # Trim empty rows at the end if necessary, but keep it simple for now
                if any(row_text):
                    rows_data.append(row_text)
                    if len(row_text) > max_cols:
                        max_cols = len(row_text)
            
            blocks = []
            if rows_data:
                blocks.append(TableBlock(rows=rows_data, columns=max_cols, block_id=f"sheet_{i}"))
            
            pages.append(PageNode(page_number=i+1, blocks=blocks, metadata={"sheet_name": sheet_name}))
        
        return DocumentStructure(
            source_path=str(file_path),
            file_type="xlsx",
            pages=pages,
            metadata={"total_sheets": len(pages)}
        )
