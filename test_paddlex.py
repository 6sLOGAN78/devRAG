import os
os.environ["FLAGS_use_mkldnn"] = "0"
import paddlex as pdx
import cv2

pipeline = pdx.create_pipeline("layout_parsing")
img = cv2.imread("tests/fixtures/scanned_sample.png")
res = pipeline.predict(img)
for r in res:
    print(r.keys())
