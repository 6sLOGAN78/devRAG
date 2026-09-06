from transformers import TableTransformerForObjectDetection
import torch
import cv2

model = TableTransformerForObjectDetection.from_pretrained("microsoft/table-transformer-structure-recognition")
print("Model loaded successfully!")
