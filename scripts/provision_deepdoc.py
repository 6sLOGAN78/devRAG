"""Acquire only explicitly approved model bytes; never runs inside the parsing service."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path

from scripts.probe.phase6_admission import PHASE, audit_packet, validate_approval

ROOT = Path(__file__).resolve().parents[1]


def provision(directory: Path, *, asr: bool = False) -> None:
    report = audit_packet(PHASE)
    validate_approval(json.loads((PHASE / "06-APPROVAL.json").read_text()), report)
    manifest = json.loads((ROOT / ("deepdoc/asr-model.json" if asr else "deepdoc/models.json")).read_text())
    if manifest["revision"] != report["models"]["asr" if asr else "deepdoc"]:
        raise ValueError("model revision differs from approved evidence")
    evidence = json.loads((PHASE / "06-SOURCE-EVIDENCE.json").read_text())["asr_model" if asr else "deepdoc"]
    approved = {item["rfilename"]: item for item in evidence["files"]}
    if asr and set(manifest["files"]) != set(approved):
        raise ValueError("model file list differs from approved evidence")
    directory.mkdir(parents=True, exist_ok=True)
    for name, spec in manifest["files"].items():
        source = approved[name]
        digest = source["lfs"]["sha256"] if "lfs" in source else spec["sha256"] if asr else evidence["ocr_dictionary"]["sha256"]
        blob = source["blobId"] if asr and "lfs" not in source else None
        if spec != {"sha256": digest, "bytes": source["size"]}:
            raise ValueError("model manifest differs from approved evidence")
        target = directory / name
        if target.is_symlink():
            raise ValueError("model target must not be a symlink")
        if target.is_file() and target.stat().st_size == spec["bytes"]:
            with target.open("rb") as cached:
                matches = hashlib.file_digest(cached, "sha256").hexdigest() == digest
            if blob:
                # Git object identity is additional to the pinned SHA-256 integrity check.
                matches = matches and hashlib.sha1(f"blob {spec['bytes']}\0".encode() + target.read_bytes(), usedforsecurity=False).hexdigest() == blob
            if matches:
                print(f"verified cached model: {name}", flush=True)
                continue
        repository = "Systran/faster-whisper-tiny" if asr else "InfiniFlow/deepdoc"
        url = f"https://huggingface.co/{repository}/resolve/{manifest['revision']}/{name}"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
                temporary = Path(output.name)
                checksum, count = hashlib.sha256(), 0
                with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - fixed HTTPS registry URL
                    while chunk := response.read(1024 * 1024):
                        count += len(chunk)
                        if count > spec["bytes"]:
                            raise ValueError("model size exceeds approved manifest")
                        checksum.update(chunk)
                        output.write(chunk)
                if count != spec["bytes"] or checksum.hexdigest() != digest:
                    raise ValueError("download differs from approved model")
                output.flush()
                os.fsync(output.fileno())
            if blob and hashlib.sha1(f"blob {count}\0".encode() + temporary.read_bytes(), usedforsecurity=False).hexdigest() != blob:
                raise ValueError("download differs from approved git blob")
            temporary.chmod(0o644)
            temporary.replace(target)
            print(f"acquired and hash-verified model: {name} ({count} bytes)", flush=True)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "ragflow-logs/deepdoc-models")
    parser.add_argument("--asr", action="store_true", help="Provision the approved local speech snapshot in output-dir/asr")
    args = parser.parse_args()
    provision(args.output_dir / "asr" if args.asr else args.output_dir, asr=args.asr)


if __name__ == "__main__":
    main()
