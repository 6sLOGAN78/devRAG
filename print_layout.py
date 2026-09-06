import paddlex as pdx
import cv2
import json
pipeline = pdx.create_pipeline("layout_parsing")
img = cv2.imread("tests/fixtures/scanned_sample.png")
res = pipeline.predict(img)
for r in res:
    # r is a dict, print keys and some contents
    print("Keys:", r.keys())
    print("Boxes:", r.get('dt_polys', []))
    print("Layout Res:", r.get('layout_res', []))
    try:
        from paddlex.utils import logging
        print("Done")
    except:
        pass
