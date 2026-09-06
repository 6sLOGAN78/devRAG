import paddlex as pdx
import cv2

try:
    pipeline = pdx.create_pipeline("layout_parsing")
    img = cv2.imread("tests/fixtures/scanned_sample.png")
    res = pipeline.predict(img)
    for r in res:
        print(r)
except Exception as e:
    print(f"Error: {e}")
