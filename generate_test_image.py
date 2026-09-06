import cv2
import numpy as np
from pathlib import Path

Path("tests/fixtures").mkdir(parents=True, exist_ok=True)
img = np.zeros((200, 400, 3), dtype=np.uint8)
img.fill(255) # white background
# Add some text
cv2.putText(img, "Invoice Number: 12345", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
cv2.putText(img, "Total Amount: $500", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)

cv2.imwrite("tests/fixtures/scanned_sample.png", img)
