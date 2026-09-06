from pathlib import Path
from typing import List, Dict, Any, Optional
import cv2

from pydantic import BaseModel

from ..models import TextBlock, PageNode
from ..errors import InvalidInputError, ParsingFailureError

class LayoutRegion(BaseModel):
    label: str
    bbox: List[float] # [xmin, ymin, xmax, ymax]
    confidence: float

class LayoutRecognizer:
    def __init__(self, model_path: str = "assets/layout/yolov8_layout.pt", confidence_threshold: float = 0.5, device: str = "cpu"):
        self.threshold = confidence_threshold
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ParsingFailureError("ultralytics is not installed. Please install it.")
        
        if not Path(model_path).exists():
            raise ParsingFailureError(f"Model weights not found at {model_path}. Please download them first.")
            
        try:
            self._model = YOLO(model_path)
            self._model.to(device)
            # Define DocLayNet class mapping to DeepDoc categories
            self.class_mapping = {
                "Page-header": "header",
                "Page-footer": "footer",
                "Title": "title",
                "Section-header": "title",
                "Text": "paragraph/text",
                "List-item": "paragraph/text",
                "Caption": "paragraph/text",
                "Footnote": "paragraph/text",
                "Picture": "figure",
                "Formula": "figure",
                "Table": "table"
            }
        except Exception as e:
            raise ParsingFailureError(f"Failed to initialize layout model: {e}")

    def detect(self, image_path: Path) -> List[LayoutRegion]:
        if not image_path.exists() or not image_path.is_file():
            raise InvalidInputError(f"Image not found or invalid path: {image_path}")
            
        img = cv2.imread(str(image_path))
        if img is None:
            raise InvalidInputError(f"Unsupported image format or corrupt file: {image_path}")
            
        try:
            results = self._model(img, verbose=False)
        except Exception as e:
            raise ParsingFailureError(f"Layout inference failed: {e}")
            
        regions = []
        for r in results:
            boxes = r.boxes
            if boxes is None:
                continue
            for box in boxes:
                conf = float(box.conf[0].item())
                if conf < self.threshold:
                    continue
                    
                cls_id = int(box.cls[0].item())
                raw_label = self._model.names[cls_id]
                mapped_label = self.class_mapping.get(raw_label, "unknown")
                
                bbox = box.xyxy[0].tolist() # [xmin, ymin, xmax, ymax]
                
                regions.append(LayoutRegion(
                    label=mapped_label,
                    bbox=bbox,
                    confidence=conf
                ))
                
        return regions

def get_intersection_over_area(box1: List[float], box2: List[float]) -> float:
    # box1 is [xmin, ymin, xmax, ymax] (the OCR block)
    # box2 is the layout region
    x_left = max(box1[0], box2[0])
    y_top = max(box1[1], box2[1])
    x_right = min(box1[2], box2[2])
    y_bottom = min(box1[3], box2[3])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    
    if box1_area == 0:
        return 0.0
        
    return intersection_area / box1_area

def build_structured_page(page_number: int, ocr_blocks: List[TextBlock], layout_regions: List[LayoutRegion], iou_threshold: float = 0.5) -> PageNode:
    """
    Correlates OCR TextBlocks with LayoutRegions to build a structured reading order PageNode.
    """
    region_blocks: Dict[int, List[TextBlock]] = {i: [] for i in range(len(layout_regions))}
    unassigned_blocks: List[TextBlock] = []

    for block in ocr_blocks:
        if block.bbox is None:
            unassigned_blocks.append(block)
            continue
            
        best_region_idx = -1
        best_overlap = 0.0
        
        for idx, region in enumerate(layout_regions):
            overlap = get_intersection_over_area(block.bbox, region.bbox)
            if overlap > best_overlap:
                best_overlap = overlap
                best_region_idx = idx
                
        if best_overlap >= iou_threshold and best_region_idx != -1:
            block.metadata["layout_type"] = layout_regions[best_region_idx].label
            block.metadata["layout_confidence"] = float(layout_regions[best_region_idx].confidence)
            region_blocks[best_region_idx].append(block)
        else:
            block.metadata["layout_type"] = "unknown"
            unassigned_blocks.append(block)

    final_blocks = []
    
    def center(bbox):
        return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)

    header_regions = [i for i, r in enumerate(layout_regions) if r.label == "header"]
    footer_regions = [i for i, r in enumerate(layout_regions) if r.label == "footer"]
    main_regions = [i for i, r in enumerate(layout_regions) if r.label not in ["header", "footer"]]
    
    header_regions.sort(key=lambda i: center(layout_regions[i].bbox)[1])
    footer_regions.sort(key=lambda i: center(layout_regions[i].bbox)[1])
    
    # Robust multi-column grouping
    # We group regions into columns based on their x-center position.
    # Two regions belong to the same column if their x-centers are close relative to their width.
    columns = []
    
    for i in main_regions:
        r_box = layout_regions[i].bbox
        r_cx = center(r_box)[0]
        r_w = r_box[2] - r_box[0]
        
        placed = False
        for col in columns:
            # Check if this region fits in this column (center falls within the column bounds approx)
            col_cx_avg = sum(center(layout_regions[idx].bbox)[0] for idx in col) / len(col)
            # If the center is within 50% of the width of the column average, group it
            if abs(r_cx - col_cx_avg) < max(r_w * 0.5, 100):
                col.append(i)
                placed = True
                break
        if not placed:
            columns.append([i])
            
    # Sort columns left to right based on average x-center
    columns.sort(key=lambda col: sum(center(layout_regions[idx].bbox)[0] for idx in col) / len(col))
    
    def add_blocks(region_idx_list):
        for idx in region_idx_list:
            blocks_in_reg = region_blocks[idx]
            # sort blocks within this region top to bottom
            blocks_in_reg.sort(key=lambda b: (b.bbox[1] if b.bbox else 0))
            final_blocks.extend(blocks_in_reg)

    add_blocks(header_regions)
    for col in columns:
        # Sort regions within column top to bottom
        col.sort(key=lambda i: center(layout_regions[i].bbox)[1])
        add_blocks(col)
        
    add_blocks(footer_regions)
    
    unassigned_blocks.sort(key=lambda b: (b.bbox[1] if b.bbox else 0))
    final_blocks.extend(unassigned_blocks)
    
    return PageNode(
        page_number=page_number,
        blocks=final_blocks,
        metadata={"total_regions": len(layout_regions)}
    )
