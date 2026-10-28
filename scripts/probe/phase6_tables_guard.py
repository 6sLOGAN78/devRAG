"""Five-repeat fixed table guard, inside the approved native image with read-only mounts."""

import base64
import hashlib
import json
import math
import resource
import statistics
import time
from pathlib import Path

from deepdoc.geometry import iou
from deepdoc.model_runtime import ModelRuntime
from deepdoc.native_runtime import NativeRuntime

root = Path("/fixtures")
annotation = json.loads((root / "table-spanned-original.json").read_text())
content = (root / "table-spanned-original.pdf").read_bytes()
if hashlib.sha256(content).hexdigest() != annotation["sha256"]:
    raise SystemExit("fixed fixture digest mismatch")
started = time.perf_counter()
runtime = NativeRuntime(ModelRuntime(Path("/models")))
load = time.perf_counter() - started
samples = []
for repetition in range(5):
    started = time.perf_counter()
    result = runtime.process_pdf("parse", content, {"layout": True})
    elapsed = time.perf_counter() - started
    blocks = [b for b in result["blocks"] if b.get("table")]
    quality = len(blocks) == 2
    evidence = []
    for page, block in enumerate(blocks, 1):
        table = block["table"]
        cells = {(c["row"], c["column"]): c for c in table["cells"]}
        box = block["boxes"][0]
        asset = block["assets"][0]
        source = base64.b64decode(asset["content_base64"], validate=True)
        crop = (box["x0"], box["top"], box["x1"], box["bottom"])
        quality = quality and table["rows"] == 5 and table["columns"] == 3 and cells[(0, 0)]["text"] == annotation["merged_header"]["text"] and cells[(0, 0)]["colspan"] == 3
        quality = quality and [cells[(1, c)]["text"] for c in range(3)] == annotation["column_headers"]
        quality = quality and [[cells[(r, c)]["text"] for c in range(3)] for r in range(2, 5)] == annotation["body_rows_by_page"][str(page)]
        quality = quality and iou(crop, tuple(annotation["table_box"])) >= annotation["minimum_crop_iou"] and box["page"] == asset["page"] == page and asset["kind"] == "table"
        quality = quality and hashlib.sha256(source).hexdigest() == asset["sha256"] == table["asset_sha256"] and source.startswith(b"\x89PNG\r\n\x1a\n")
        quality = quality and "<b>Literal</b>" not in table["html"] and "&lt;b&gt;Literal&lt;/b&gt;" in table["html"]
        evidence.append(
            {
                "page": page,
                "source_box": crop,
                "cells": table["cells"],
                "html": table["html"],
                "crop_sha256": asset["sha256"],
                "crop_bytes": len(source),
                "crop_dimensions": [asset["width"], asset["height"]],
            }
        )
    samples.append(
        {
            "repetition": repetition + 1,
            "seconds": elapsed,
            "per_page_seconds": elapsed / 2,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "quality_pass": quality,
            "tables": evidence,
        }
    )
stable_crops = all(len({sample["tables"][page]["crop_sha256"] for sample in samples}) == 1 for page in range(2))
times = sorted(sample["per_page_seconds"] for sample in samples)
report = {
    "fixture_sha256": annotation["sha256"],
    "deterministic_crops": stable_crops,
    "network": "none",
    "cpu_quota": 2,
    "memory_cap_mib": 3072,
    "model_load_seconds": load,
    "p50_per_page_seconds": statistics.median(times),
    "p95_per_page_seconds": times[math.ceil(len(times) * 0.95) - 1],
    "peak_rss_mib": max(s["peak_rss_kib"] for s in samples) / 1024,
    "samples": samples,
}
print(json.dumps(report, indent=2))
if not stable_crops or not all(sample["quality_pass"] for sample in samples):
    raise SystemExit("fixed table quality guard failed")
if report["p95_per_page_seconds"] > 30:
    raise SystemExit("table latency guard failed")
