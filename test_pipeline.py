from deepdoc.vision.ocr import OcrEngine
from deepdoc.vision.layout_recognizer import LayoutRecognizer, build_structured_page
from pathlib import Path

img_path = Path("tests/fixtures/multi_column_sample.png")

ocr_engine = OcrEngine()
blocks = ocr_engine.extract(img_path)

layout_recognizer = LayoutRecognizer(model_path="assets/layout/yolov8_layout.pt")
regions = layout_recognizer.detect(img_path)

page = build_structured_page(1, blocks, regions)

for b in page.blocks:
    print(f"[{b.metadata.get('layout_type', 'unknown')}] {b.text}")

