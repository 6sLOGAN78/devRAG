import os
from pathlib import Path

docs_dir = Path("ragflow-docs")
for root, dirs, files in os.walk(docs_dir):
    for name in files:
        if name.endswith(".md"):
            path = Path(root) / name
            print(f"\n--- {path} ---")
            with open(path, "r") as f:
                content = f.read()
                if len(content) > 500:
                    print(content[:500] + "\n...[truncated]")
                else:
                    print(content)
