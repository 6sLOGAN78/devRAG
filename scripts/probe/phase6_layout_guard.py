"""Run inside the isolated native image with /models and /fixtures mounted read-only."""

import hashlib
import json
import math
import resource
import statistics
import time
from pathlib import Path

from deepdoc.model_runtime import ModelRuntime
from deepdoc.native_runtime import NativeRuntime

root = Path("/fixtures")
annotation = json.loads((root / "layout-two-column.json").read_text())
content = (root / "layout-two-column.pdf").read_bytes()
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
    text = "\n".join(b["text"] for b in result["blocks"])
    positions = [text.find(marker) for marker in annotation["reading_order"]]
    quality = (
        all(i >= 0 for i in positions)
        and positions == sorted(positions)
        and not any(marker in text for marker in annotation["remove"])
        and result["report"]["layout_backend"] == "deepdoc-onnx"
        and result["report"]["layout_regions"] > 0
    )
    samples.append(
        {
            "repetition": repetition + 1,
            "seconds": elapsed,
            "per_page_seconds": elapsed / annotation["pages"],
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "quality_pass": quality,
            "result": result,
        }
    )
times = sorted(s["per_page_seconds"] for s in samples)
report = {
    "fixture_sha256": annotation["sha256"],
    "network": "none",
    "model_load_seconds": load,
    "cpu_quota": 2,
    "memory_cap_mib": 3072,
    "p50_per_page_seconds": statistics.median(times),
    "p95_per_page_seconds": times[math.ceil(len(times) * 0.95) - 1],
    "peak_rss_mib": max(s["peak_rss_kib"] for s in samples) / 1024,
    "samples": samples,
}
print(json.dumps(report, indent=2))
if not all(s["quality_pass"] for s in samples):
    raise SystemExit("fixed layout quality guard failed")
if report["p95_per_page_seconds"] > 30:
    raise SystemExit("approved latency guard exceeded")
