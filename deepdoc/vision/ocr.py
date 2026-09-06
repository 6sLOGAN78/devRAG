from pathlib import Path

import cv2

from ..errors import InvalidInputError, ParsingFailureError
from ..models import TextBlock


class OcrEngine:
    """
    Wrapper for PaddleOCR.
    Extracts text from images and normalizes the results into DeepDoc TextBlock models.
    """
    def __init__(self, lang: str = "en", use_gpu: bool = False):
        try:
            from paddleocr import PaddleOCR
        except ImportError:
            raise ParsingFailureError("PaddleOCR is not installed. Please install it.")
        
        device = "gpu" if use_gpu else "cpu"
        # We set enable_mkldnn=False because of a known runtime bug in the underlying paddlepaddle implementation.
        self._engine = PaddleOCR(use_textline_orientation=True, lang=lang, device=device, enable_mkldnn=False)

    def extract(self, image_path: Path) -> list[TextBlock]:
        if not image_path.exists() or not image_path.is_file():
            raise InvalidInputError(f"Image not found or invalid path: {image_path}")

        image = cv2.imread(str(image_path))
        if image is None:
            raise InvalidInputError(f"Unsupported image format or corrupt file: {image_path}")
            
        try:
            results = self._engine.predict(image)
        except Exception as e:
            raise ParsingFailureError(f"OCR Inference failed: {e}")
            
        blocks = []
        block_idx = 0
        
        for res in results:
            polys = res.get('dt_polys', [])
            texts = res.get('rec_texts', [])
            scores = res.get('rec_scores', [])
            
            for i in range(len(texts)):
                text = texts[i]
                score = scores[i] if i < len(scores) else 0.0
                poly = polys[i] if i < len(polys) else None
                
                bbox = None
                if poly is not None and len(poly) > 0:
                    x_coords = [point[0] for point in poly]
                    y_coords = [point[1] for point in poly]
                    
                    xmin = float(min(x_coords))
                    ymin = float(min(y_coords))
                    xmax = float(max(x_coords))
                    ymax = float(max(y_coords))
                    bbox = [xmin, ymin, xmax, ymax]
                    
                blocks.append(TextBlock(
                    text=text,
                    block_id=f"ocr_block_{block_idx}",
                    bbox=bbox,
                    metadata={
                        "confidence": float(score),
                        "source": "paddleocr"
                    }
                ))
                block_idx += 1
                
        return blocks
