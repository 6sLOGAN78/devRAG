from paddleocr import PaddleOCR
import cv2
img = cv2.imread("tests/fixtures/scanned_sample.png")
try:
    engine = PaddleOCR(use_textline_orientation=True, lang="en", device="cpu", enable_mkldnn=False)
except ValueError:
    print("enable_mkldnn not supported")
    engine = PaddleOCR(use_textline_orientation=True, lang="en", device="cpu")
res = engine.predict(img)
for r in res:
    print(r)
    print("Boxes:", r.get('dt_polys', []))
    print("Texts:", r.get('rec_texts', []))
    print("Scores:", r.get('rec_scores', []))
