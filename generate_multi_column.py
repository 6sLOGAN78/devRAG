import cv2
import numpy as np

img = np.zeros((600, 800, 3), dtype=np.uint8)
img.fill(255)

# Header
cv2.putText(img, "Annual Report 2024", (300, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
# Column 1
cv2.putText(img, "Revenue increased", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
cv2.putText(img, "by 20% in Q1.", (50, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
cv2.putText(img, "Market share is", (50, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
cv2.putText(img, "growing steadily.", (50, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

# Column 2
cv2.putText(img, "Costs were reduced", (450, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
cv2.putText(img, "by optimization.", (450, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
cv2.putText(img, "New products will", (450, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
cv2.putText(img, "launch in Q3.", (450, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

# Footer
cv2.putText(img, "Page 1", (380, 580), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

cv2.imwrite("tests/fixtures/multi_column_sample.png", img)
