"""Measure the real local TEI CPU backend; never call an external inference API.

Run with ``uv run python -m scripts.probe.time_rerank``. The driver, batch size and
docs text are the same ones used by the application. No latency is assumed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
import subprocess
import threading
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from common.settings import LlmSettings
from rag.llm import resolve_provider
from rag.llm.rerank_model import TEIRerank
from rag.nlp.token_count import count_tokens, truncate_tokens

ROOT = Path(__file__).resolve().parents[2]
SIZES = (16, 32, 64, 128, 256, 1024)


def percentile(values: Sequence[float], q: float) -> float:
    if not values or not 0 <= q <= 1 or any(not math.isfinite(v) for v in values):
        raise ValueError("finite samples and a quantile in [0, 1] are required")
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def choose_cap(rows: Sequence[dict[str, Any]], budget_seconds: float = 10.0, length: str = "512") -> int | None:
    candidates = [int(row["n"]) for row in rows if str(row["length"]) == length and float(row["p95"]) <= budget_seconds]
    return max(candidates, default=None)


def choose_mem_limit(peak_mib: float) -> str:
    if not math.isfinite(peak_mib) or peak_mib <= 0:
        raise ValueError("positive finite peak memory is required")
    return f"{math.ceil(peak_mib * 1.25 / 256) * 256}m"


def docker(*args: str) -> str:
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True, timeout=120).stdout.strip()


def memory_mib(value: str) -> float:
    match = re.fullmatch(r"([0-9.]+)\s*(B|kB|KiB|MB|MiB|GB|GiB)", value.strip())
    if match is None:
        raise ValueError("unrecognised Docker memory unit")
    factor = {"B": 1 / 1048576, "kB": 1000 / 1048576, "KiB": 1 / 1024, "MB": 1000000 / 1048576, "MiB": 1, "GB": 1000000000 / 1048576, "GiB": 1024}
    return float(match[1]) * factor[match[2]]


class MemorySampler:
    def __init__(self, container: str) -> None:
        self.container = container
        self.peak = 0.0
        self.error: str | None = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self) -> None:
        while not self.stop.is_set():
            try:
                usage = docker("stats", "--no-stream", "--format", "{{.MemUsage}}", self.container)
                self.peak = max(self.peak, memory_mib(usage.split("/")[0]))
            except (OSError, subprocess.SubprocessError, ValueError):
                self.error = "Docker memory sampling failed"
                return
            self.stop.wait(0.25)


def docs_text(length: int) -> str:
    paths = [ROOT / "docs/07-retrieval/reranking.md", ROOT / "docs/05-rag-pipeline/parsing.md"]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    if count_tokens(text) < length:
        raise ValueError("documentation corpus is too short")
    return truncate_tokens(text, length)


def cold_start(container: str, base: str) -> float:
    start = time.monotonic()
    docker("restart", container)
    deadline = start + 300
    with httpx.Client(timeout=3) as client:
        while time.monotonic() < deadline:
            try:
                if client.get(f"{base}/health").status_code == 200:
                    return time.monotonic() - start
            except httpx.HTTPError:
                pass
            threading.Event().wait(0.25)
    raise TimeoutError("TEI did not become healthy after the measured restart")


async def measure(
    base: str, container: str, checkpoint: Path, *, sizes: Sequence[int] = SIZES, lengths: Sequence[int] = (128, 512),
) -> tuple[list[dict[str, Any]], float]:
    driver = TEIRerank(
        resolve_provider("TEI"), os.environ.get("TEI_RERANK_MODEL", "BAAI/bge-reranker-base"), None, base,
        llm_settings=LlmSettings(max_retries=0), allow_private=True, timeout=120,
    )
    rows: list[dict[str, Any]] = []
    sampler = MemorySampler(container)
    sampler.thread.start()
    try:
        for length in lengths:
            text = await asyncio.to_thread(docs_text, length)
            for n in sizes:
                timings = []
                for _ in range(5):
                    start = time.monotonic()
                    result = await driver.similarity("How are documents processed and reranked?", [text] * n)
                    timings.append(time.monotonic() - start)
                    if len(result.scores) != n:
                        raise RuntimeError("TEI returned an incomplete batch")
                row = {"n": n, "length": str(length), "tokens": count_tokens(text), "seconds": timings, "p50": percentile(timings, 0.5), "p95": percentile(timings, 0.95)}
                row["pairs_per_second"] = n / row["p50"]
                rows.append(row)
                await asyncio.to_thread(checkpoint.write_text, json.dumps({"rows": rows, "peak_mib": sampler.peak}, indent=2) + "\n")
                print(f"N={n} tokens={length} p50={row['p50']:.3f}s p95={row['p95']:.3f}s", flush=True)
    finally:
        sampler.stop.set()
        await asyncio.to_thread(sampler.thread.join, 125)
    if sampler.error or sampler.peak <= 0:
        raise RuntimeError(sampler.error or "no memory samples were recorded")
    return rows, sampler.peak


def render(rows: list[dict[str, Any]], peak: float, cold: float, image_bytes: int, volume: str, backend: str) -> str:
    cap = choose_cap(rows)
    lines = [
        "# Phase 5 real CPU rerank timing (R-219)", "",
        f"Measured {datetime.now(timezone.utc).isoformat()} through the production TEIRerank driver, batches of 32, five repetitions per row.",
        "The input is repository documentation cut with count_tokens to the stated cl100k token lengths; TEI uses its own tokenizer and truncates at its model limit.", "",
        "| Pairs | Chunk tokens | p50 seconds | p95 seconds | Pairs/second |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| {row['n']} | {row['tokens']} | {row['p50']:.4f} | {row['p95']:.4f} | {row['pairs_per_second']:.2f} |")
    lines.extend([
        "", f"Chosen rerank cap at p95 <= 10 s for 512-token chunks: **{cap}**.",
        f"Peak sampled container memory: **{peak:.2f} MiB** (docker stats working-set proxy for RSS, sampled throughout the run).",
        f"Memory limit with 25% headroom rounded up to 256 MiB: **{choose_mem_limit(peak)}**.",
        f"Restart-to-health with weights already cached: **{cold:.3f} seconds**.",
        f"Image uncompressed size: **{image_bytes} bytes**.",
        f"Model volume: `{volume}`.", f"Backend startup log: `{backend}`.",
        "The retrieval pool remains top_k = 1024; only the cross-encoder window is capped.", "",
    ])
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=int(os.environ.get("TEI_PORT", "6381")))
    ap.add_argument("--container", default="devrag-stack-tei-1")
    ap.add_argument("--guard-only", action="store_true", help="Measure only the smallest 512-token window before a long full run")
    ap.add_argument("--output", type=Path, default=ROOT / ".planning/phases/05-retrieval-and-cited-chat-core-value-gate/05-RERANK-TIMING.md")
    args = ap.parse_args()
    base = f"http://127.0.0.1:{args.port}"
    cold = cold_start(args.container, base)
    checkpoint = args.output.with_suffix(".samples.json")
    options = {"sizes": (16,), "lengths": (512,)} if args.guard_only else {}
    rows, peak = asyncio.run(measure(base, args.container, checkpoint, **options))
    image_id = docker("inspect", "--format", "{{.Image}}", args.container)
    image_bytes = int(docker("image", "inspect", "--format", "{{.Size}}", image_id))
    volumes = docker("system", "df", "-v")
    volume = next((line for line in volumes.splitlines() if "tei_data" in line), "not reported")
    # Startup logs contain no inference inputs or credentials. Retain one backend line only.
    logs = docker("logs", args.container)
    backend_lines = (line for line in logs.splitlines() if "backend" in line.lower() and ("onnx" in line.lower() or "candle" in line.lower()))
    backend = next(backend_lines, "No backend name in stdout; inspect container startup logs")
    backend = re.sub(r"\x1b\[[0-9;]*m", "", backend).replace("`", "'")
    args.output.write_text(render(rows, peak, cold, image_bytes, volume, backend))
    print(f"cap={choose_cap(rows)} memory={choose_mem_limit(peak)} evidence={args.output.name}")


if __name__ == "__main__":
    main()
