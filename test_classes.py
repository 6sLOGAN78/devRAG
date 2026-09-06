from ultralytics import YOLO
model = YOLO("assets/layout/yolov8_layout.pt")
print(model.names)
