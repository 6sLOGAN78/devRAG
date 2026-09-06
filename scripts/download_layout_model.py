from huggingface_hub import hf_hub_download
import shutil
import sys
from pathlib import Path

repo_id = "vaivTA/yolov8n_doclaynet"
filename = "weights/best.pt"

print(f"Downloading {filename} from {repo_id}...")
try:
    path = hf_hub_download(repo_id=repo_id, filename=filename)
    dest = Path("assets/layout/yolov8_layout.pt")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(path, dest)
    print(f"Model downloaded and saved to {dest}")
except Exception as e:
    print(f"Failed to download model: {e}")
    sys.exit(1)
