from deepdoc.vision.ocr import OcrEngine
from deepdoc.vision.table_structure_recognizer import TableStructureRecognizer
from PIL import Image
import numpy as np
import cv2
from pathlib import Path

img_path = Path("tests/fixtures/financial_table.png")
print("Running OCR...")
ocr = OcrEngine()
blocks = ocr.extract(img_path)

print("Running TSR...")
recognizer = TableStructureRecognizer(model_path="microsoft/table-transformer-structure-recognition", cache_dir="assets/table")

img = Image.open(img_path)
page_bbox = [0, 0, img.width, img.height]

table = recognizer.recognize(img, page_bbox, blocks)

print("\n--- HTML ---")
print(table.to_html())
print("\n--- MARKDOWN ---")
print(table.to_markdown())
