from ultralytics import YOLO
import cv2

model = YOLO("assets/layout/yolov8_layout.pt")
print("Model classes:", model.names)

img = cv2.imread("tests/fixtures/scanned_sample.png")
results = model(img)
for r in results:
    boxes = r.boxes
    for box in boxes:
        cls_id = int(box.cls[0].item())
        print(f"Class: {model.names[cls_id]}, Conf: {box.conf[0].item():.2f}, Box: {box.xyxy[0].tolist()}")
