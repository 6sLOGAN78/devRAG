import pytest
from deepdoc.models import TableStructure, TableRow, TableCell, TextBlock
from deepdoc.vision.table_structure_recognizer import TableStructureRecognizer
import numpy as np
from PIL import Image
from unittest.mock import patch, MagicMock

def test_table_structure_models():
    cell1 = TableCell(text="Revenue", row_index=0, column_index=0)
    cell2 = TableCell(text="2024", row_index=0, column_index=1)
    cell3 = TableCell(text="100", row_index=1, column_index=0)
    cell4 = TableCell(text="200", row_index=1, column_index=1)
    
    row1 = TableRow(cells=[cell1, cell2])
    row2 = TableRow(cells=[cell3, cell4])
    
    table = TableStructure(rows=[row1, row2], columns=2)
    
    md = table.to_markdown()
    assert "| Revenue | 2024 |" in md
    assert "| --- | --- |" in md
    assert "| 100 | 200 |" in md
    
    html = table.to_html()
    assert "<td>Revenue</td>" in html
    assert "<td>200</td>" in html

def test_merged_cells_html():
    cell1 = TableCell(text="Revenue", row_index=0, column_index=0, column_span=2)
    row1 = TableRow(cells=[cell1])
    table = TableStructure(rows=[row1], columns=2)
    html = table.to_html()
    assert '<td colspan="2">Revenue</td>' in html

@patch("transformers.TableTransformerForObjectDetection.from_pretrained")
@patch("transformers.AutoImageProcessor.from_pretrained")
def test_tsr_grid_reconstruction(MockProcessor, MockModel):
    # Mock model
    mock_model = MagicMock()
    MockModel.return_value = mock_model
    
    mock_processor = MagicMock()
    mock_processor.return_value = MagicMock(to=lambda d: {"pixel_values": "dummy"})
    
    import torch
    
    # We will simulate the post_process output
    # Classes: 1: col, 2: row, 5: span
    # 2 rows, 2 columns, 1 span spanning col 0 and col 1 on row 0
    mock_processor.post_process_object_detection.return_value = [{
        "boxes": torch.tensor([
            [0, 0, 50, 100],   # col 0
            [50, 0, 100, 100], # col 1
            [0, 0, 100, 50],   # row 0
            [0, 50, 100, 100], # row 1
            [0, 0, 100, 50]    # span over row 0, col 0 and 1
        ]),
        "scores": torch.tensor([0.9, 0.9, 0.9, 0.9, 0.9]),
        "labels": torch.tensor([1, 1, 2, 2, 5])
    }]
    
    MockProcessor.return_value = mock_processor
    
    recognizer = TableStructureRecognizer()
    
    img = Image.new("RGB", (100, 100))
    page_bbox = [0, 0, 100, 100]
    
    ocr_blocks = [
        TextBlock(text="MergedHeader", bbox=[10, 10, 90, 40]),
        TextBlock(text="CellA", bbox=[10, 60, 40, 90]),
        TextBlock(text="CellB", bbox=[60, 60, 90, 90])
    ]
    
    table = recognizer.recognize(img, page_bbox, ocr_blocks)
    
    assert table.columns == 2
    assert len(table.rows) == 2
    
    row0_cells = table.rows[0].cells
    assert len(row0_cells) == 1
    assert row0_cells[0].row_span == 1
    assert row0_cells[0].column_span == 2
    assert row0_cells[0].text == "MergedHeader"
    
    row1_cells = table.rows[1].cells
    assert len(row1_cells) == 2
    assert row1_cells[0].text == "CellA"
    assert row1_cells[1].text == "CellB"
