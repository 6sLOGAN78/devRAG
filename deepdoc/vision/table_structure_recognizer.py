import torch
import numpy as np
from PIL import Image
from typing import List, Dict, Any, Tuple
from pydantic import BaseModel
from pathlib import Path

from ..models import TableStructure, TableRow, TableCell, TextBlock
from ..errors import ParsingFailureError, InvalidInputError

import abc

class BaseTableStructureRecognizer(abc.ABC):
    @abc.abstractmethod
    def extract(self, image_path: Path) -> list[TableStructure]:
        pass

class HFTableStructureRecognizer(BaseTableStructureRecognizer):
    def __init__(self, model_path: str = "microsoft/table-transformer-structure-recognition", cache_dir: str = "assets/table", confidence_threshold: float = 0.5, device: str = "cpu"):
        self.threshold = confidence_threshold
        self.device = device
        
        try:
            from transformers import TableTransformerForObjectDetection, AutoImageProcessor
        except ImportError:
            raise ParsingFailureError("transformers or timm is not installed.")
            
        try:
            self.processor = AutoImageProcessor.from_pretrained(model_path, cache_dir=cache_dir)
            self.model = TableTransformerForObjectDetection.from_pretrained(model_path, cache_dir=cache_dir)
            self.model.to(self.device)
        except Exception as e:
            raise ParsingFailureError(f"Failed to load TSR model: {e}")

    def recognize(self, table_image: Image.Image | np.ndarray, page_bbox: List[float], ocr_blocks: List[TextBlock]) -> TableStructure:
        """
        table_image: cropped image of the table.
        page_bbox: [xmin, ymin, xmax, ymax] of the table in the original page coordinates.
        ocr_blocks: list of TextBlock for the whole page (or just the table).
        """
        if isinstance(table_image, np.ndarray):
            # assume BGR from cv2
            table_image = Image.fromarray(table_image[..., ::-1])
            
        inputs = self.processor(images=table_image, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self.model(**inputs)
            
        target_sizes = torch.tensor([table_image.size[::-1]]) # (height, width)
        results = self.processor.post_process_object_detection(outputs, target_sizes=target_sizes, threshold=self.threshold)[0]
        
        # classes: 1: 'table column', 2: 'table row', 3: 'table column header', 4: 'table projected row header', 5: 'table spanning cell'
        
        boxes = results["boxes"].cpu().tolist()
        scores = results["scores"].cpu().tolist()
        labels = results["labels"].cpu().tolist()
        
        rows = []
        cols = []
        spans = []
        
        for box, score, label in zip(boxes, scores, labels):
            if label == 1:
                cols.append(box)
            elif label == 2 or label == 3 or label == 4:
                rows.append(box)
            elif label == 5:
                spans.append(box)
                
        # Sort rows top-to-bottom and cols left-to-right
        rows = sorted(rows, key=lambda b: b[1])
        cols = sorted(cols, key=lambda b: b[0])
        
        if not rows or not cols:
            return TableStructure(rows=[], columns=0)
            
        # 1. Create a grid of cells
        # We define a matrix of cells
        grid = {}
        for r_idx, r_box in enumerate(rows):
            grid[r_idx] = {}
            for c_idx, c_box in enumerate(cols):
                # Intersection of row and column box
                xmin = max(r_box[0], c_box[0])
                ymin = max(r_box[1], c_box[1])
                xmax = min(r_box[2], c_box[2])
                ymax = min(r_box[3], c_box[3])
                
                # Valid box
                if xmax > xmin and ymax > ymin:
                    grid[r_idx][c_idx] = {
                        "bbox": [xmin, ymin, xmax, ymax],
                        "row_span": 1,
                        "col_span": 1,
                        "active": True
                    }
                else:
                    grid[r_idx][c_idx] = {
                        "bbox": [c_box[0], r_box[1], c_box[2], r_box[3]], # Fallback
                        "row_span": 1,
                        "col_span": 1,
                        "active": True
                    }
                    
        # 2. Merge spanning cells
        def get_intersection_area(b1, b2):
            x_left = max(b1[0], b2[0])
            y_top = max(b1[1], b2[1])
            x_right = min(b1[2], b2[2])
            y_bottom = min(b1[3], b2[3])
            if x_right < x_left or y_bottom < y_top:
                return 0.0
            return (x_right - x_left) * (y_bottom - y_top)
            
        for span_box in spans:
            span_r_start, span_r_end = -1, -1
            span_c_start, span_c_end = -1, -1
            
            # Find which rows/cols this span intersects heavily
            for r_idx, r_box in enumerate(rows):
                if get_intersection_area(span_box, r_box) > 0.3 * ((r_box[2]-r_box[0])*(r_box[3]-r_box[1])):
                     if span_r_start == -1: span_r_start = r_idx
                     span_r_end = r_idx
                     
            for c_idx, c_box in enumerate(cols):
                if get_intersection_area(span_box, c_box) > 0.3 * ((c_box[2]-c_box[0])*(c_box[3]-c_box[1])):
                     if span_c_start == -1: span_c_start = c_idx
                     span_c_end = c_idx
                     
            if span_r_start != -1 and span_c_start != -1:
                # We have a valid span over these indices
                # Disable all cells in the span except the top-left
                for r in range(span_r_start, span_r_end + 1):
                    for c in range(span_c_start, span_c_end + 1):
                        if r == span_r_start and c == span_c_start:
                            grid[r][c]["row_span"] = span_r_end - span_r_start + 1
                            grid[r][c]["col_span"] = span_c_end - span_c_start + 1
                            # Expand bounding box
                            grid[r][c]["bbox"] = [
                                min(grid[r][c]["bbox"][0], span_box[0]),
                                min(grid[r][c]["bbox"][1], span_box[1]),
                                max(grid[r][c]["bbox"][2], span_box[2]),
                                max(grid[r][c]["bbox"][3], span_box[3])
                            ]
                        else:
                            grid[r][c]["active"] = False

        # 3. Transform to Page Coordinates and create TableCells
        # page_bbox is [x_min, y_min, x_max, y_max]
        scale_x = (page_bbox[2] - page_bbox[0]) / table_image.width
        scale_y = (page_bbox[3] - page_bbox[1]) / table_image.height
        
        def to_page_coord(box):
            return [
                page_bbox[0] + box[0] * scale_x,
                page_bbox[1] + box[1] * scale_y,
                page_bbox[0] + box[2] * scale_x,
                page_bbox[1] + box[3] * scale_y
            ]

        final_cells: List[TableCell] = []
        for r_idx in sorted(grid.keys()):
            for c_idx in sorted(grid[r_idx].keys()):
                cell_data = grid[r_idx][c_idx]
                if cell_data["active"]:
                    page_box = to_page_coord(cell_data["bbox"])
                    final_cells.append(TableCell(
                        row_index=r_idx,
                        column_index=c_idx,
                        row_span=cell_data["row_span"],
                        column_span=cell_data["col_span"],
                        bbox=page_box
                    ))
                    
        # 4. Map OCR Blocks to Cells
        # Only consider OCR blocks that intersect the table_bbox
        for block in ocr_blocks:
            if not block.bbox:
                continue
            
            # Check overlap with table
            table_area = get_intersection_area(block.bbox, page_bbox)
            block_area = (block.bbox[2]-block.bbox[0]) * (block.bbox[3]-block.bbox[1])
            if block_area == 0 or (table_area / block_area) < 0.3:
                continue # Not in table
                
            best_cell = None
            best_overlap = 0
            
            for cell in final_cells:
                overlap = get_intersection_area(block.bbox, cell.bbox)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_cell = cell
                    
            if best_cell is not None and best_overlap > 0.1 * block_area:
                # Add text to cell
                # Store it in a temporary list to sort top-to-bottom later
                if "raw_blocks" not in best_cell.metadata:
                    best_cell.metadata["raw_blocks"] = []
                best_cell.metadata["raw_blocks"].append(block)

        # 5. Build final structured rows
        table_rows = []
        for r_idx in sorted(grid.keys()):
            row_cells = [c for c in final_cells if c.row_index == r_idx]
            
            # Combine raw blocks in each cell
            for cell in row_cells:
                raw_blocks = cell.metadata.pop("raw_blocks", [])
                raw_blocks.sort(key=lambda b: b.bbox[1] if b.bbox else 0)
                
                texts = [b.text.strip() for b in raw_blocks if b.text.strip()]
                # normalize newlines to single space or keep newlines based on requirement
                # Let's keep a space to avoid breaking markdown, or maybe just \n.
                # Actually, conservative joining
                cell.text = " ".join(texts)
                
            table_rows.append(TableRow(
                cells=row_cells,
                bbox=to_page_coord(rows[r_idx])
            ))
            
        return TableStructure(
            rows=table_rows,
            columns=len(cols)
        )


class DeepDocONNXTSR(BaseTableStructureRecognizer):
    def __init__(self):
        pass

    def extract(self, image_path: Path) -> list[TableStructure]:
        import logging
        logging.getLogger(__name__).warning("DeepDocONNXTSR invoked but weights not downloaded. Returning empty.")
        return []

def get_tsr_model() -> BaseTableStructureRecognizer:
    try:
        import os
        from common.settings import load_config
        cfg = load_config(os.environ.get('RAGFLOW_CONFIG', 'conf/service_conf.yaml'))
        model_name = cfg.user_default_llm.default_models.tsr_model.name
        if model_name == 'deepdoc-onnx':
            return DeepDocONNXTSR()
        return HFTableStructureRecognizer()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to load TSR model config: {e}. Falling back to HFTableStructureRecognizer.")
        return HFTableStructureRecognizer()
