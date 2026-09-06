from typing import Any

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    text: str
    block_id: str | None = None
    bbox: list[float] | None = None
    style: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class TableBlock(BaseModel):
    rows: list[list[str]]
    columns: int | None = None
    block_id: str | None = None
    bbox: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class PageNode(BaseModel):
    page_number: int
    blocks: list[TextBlock | TableBlock] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

class DocumentStructure(BaseModel):
    document_id: str | None = None
    source_path: str | None = None
    file_type: str | None = None
    pages: list[PageNode] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

class TableCell(BaseModel):
    text: str = ""
    row_index: int = 0
    column_index: int = 0
    row_span: int = 1
    column_span: int = 1
    bbox: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class TableRow(BaseModel):
    cells: list[TableCell] = Field(default_factory=list)
    bbox: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class TableStructure(BaseModel):
    rows: list[TableRow] = Field(default_factory=list)
    columns: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    def to_markdown(self) -> str:
        if not self.rows:
            return ""
            
        md = []
        for r_idx, row in enumerate(self.rows):
            # Sort cells by column_index
            cells = sorted(row.cells, key=lambda c: c.column_index)
            # Create a full row with empty strings for missing cells
            row_data = [""] * self.columns
            for cell in cells:
                text = cell.text.replace("\n", " ").replace("|", "\\|")
                if 0 <= cell.column_index < self.columns:
                    row_data[cell.column_index] = text
                    
            row_str = "| " + " | ".join(row_data) + " |"
            md.append(row_str)
            
            # Add separator after header
            if r_idx == 0:
                sep = "| " + " | ".join(["---"] * self.columns) + " |"
                md.append(sep)
                
        return "\n".join(md)
        
    def to_html(self) -> str:
        if not self.rows:
            return "<table></table>"
            
        html = ["<table>"]
        for row in self.rows:
            html.append("  <tr>")
            cells = sorted(row.cells, key=lambda c: c.column_index)
            for cell in cells:
                rs = f' rowspan="{cell.row_span}"' if cell.row_span > 1 else ""
                cs = f' colspan="{cell.column_span}"' if cell.column_span > 1 else ""
                
                # HTML escape content conservatively
                text = cell.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                html.append(f"    <td{rs}{cs}>{text}</td>")
            html.append("  </tr>")
        html.append("</table>")
        return "\n".join(html)

