from transformers import TableTransformerForObjectDetection, AutoImageProcessor
from PIL import Image
import numpy as np

img = Image.new("RGB", (800, 600), "white")
processor = AutoImageProcessor.from_pretrained("microsoft/table-transformer-structure-recognition", cache_dir="assets/table")
model = TableTransformerForObjectDetection.from_pretrained("microsoft/table-transformer-structure-recognition", cache_dir="assets/table")

inputs = processor(images=img, return_tensors="pt")
outputs = model(**inputs)

target_sizes = torch.tensor([img.size[::-1]])
results = processor.post_process_object_detection(outputs, target_sizes=target_sizes, threshold=0.9)[0]
print("Processor loaded and ran!")
