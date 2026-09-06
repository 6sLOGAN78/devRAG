from transformers import TableTransformerForObjectDetection
import sys

print("Downloading Table Transformer Structure Recognition model to assets/table...")
try:
    # This automatically downloads and caches the model
    model = TableTransformerForObjectDetection.from_pretrained("microsoft/table-transformer-structure-recognition", cache_dir="assets/table")
    print("Model downloaded successfully!")
except Exception as e:
    print(f"Failed to download model: {e}")
    sys.exit(1)
