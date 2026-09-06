import urllib.request
import cv2

url = "https://raw.githubusercontent.com/Layout-Parser/layout-parser/main/tests/fixtures/multi_column_image.jpg"
try:
    urllib.request.urlretrieve(url, "tests/fixtures/multi_column_sample.png")
except Exception as e:
    print(f"Failed to download: {e}")
