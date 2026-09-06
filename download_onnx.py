import os
from huggingface_hub import snapshot_download

model_dir = "assets/deepdoc"
os.makedirs(model_dir, exist_ok=True)
print("Downloading InfiniFlow/deepdoc ONNX models...")
snapshot_download(repo_id="InfiniFlow/deepdoc", local_dir=model_dir)
print("Download complete!")
