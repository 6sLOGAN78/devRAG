"""Read-only checks for Phase 6's exact acquisition and live-budget snapshot.

This validates a recorded decision; it cannot establish that a human made one.
There are no install, download, inference or approval-writing operations here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

PHASE = Path(__file__).resolve().parents[2] / ".planning/phases/06-deep-parsing-and-chunking-breadth"
AUDIT_FILES = (
    "06-SOURCE-EVIDENCE.json",
    "06-TRANSITIVE-EVIDENCE.json",
    "06-CANDIDATE-WHEELS.txt",
    "06-PACKAGE-SCAN.json",
    "06-TRANSITIVE-SCAN.json",
    "06-LIVE-LIMITS.json",
    "06-PACKAGES.md",
    "06-LIVE-MATRIX.md",
)
MAX_FILE_BYTES = 8 * 1024 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\]+)", re.MULTILINE)
LIMIT_KEYS = frozenset({"chat_class", "vision", "cloud_ocr", "local_asr_live", "external_parser_submissions", "query_embeddings", "embedded_chunks"})


class AdmissionError(ValueError):
    """A fixed, non-secret failure code suitable for a checkpoint log."""


def _read(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise AdmissionError("audit_file_too_large")
    return data


def _json(data: bytes) -> Any:
    try:
        return json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise AdmissionError("audit_json_invalid") from None


def _name(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise AdmissionError("package_name_invalid")
    return re.sub(r"[-_.]+", "-", name).lower()


def _pins(rows: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        name, version = _name(row["name"]), row["version"]
        if name in result or not isinstance(version, str) or not version.strip():
            raise AdmissionError("package_version_invalid")
        result[name] = version
    return result


def _scan(rows: list[dict[str, Any]], packages: dict[str, str]) -> Counter[str]:
    seen = set()
    counts: Counter[str] = Counter()
    for row in rows:
        name, status = _name(row["package"]), row["status"]
        if name in seen or status not in {"OK", "SUS"}:
            raise AdmissionError("package_scan_refused")
        seen.add(name)
        counts[status] += 1
    if seen != set(packages):
        raise AdmissionError("package_scan_incomplete")
    return counts


def _weight(row: dict[str, Any]) -> None:
    if type(row.get("size")) is not int or row["size"] <= 0 or not SHA256.fullmatch(row.get("lfs", {}).get("sha256", "")):
        raise AdmissionError("model_weight_manifest_invalid")


def audit_packet(directory: Path) -> dict[str, Any]:
    """Check metadata completeness and bind the review packet to its exact bytes."""
    raw = {name: _read(directory / name) for name in AUDIT_FILES}
    try:
        source = _json(raw["06-SOURCE-EVIDENCE.json"])
        direct = _pins(source["selected_package_candidates"])
        metadata = _pins(_json(raw["06-TRANSITIVE-EVIDENCE.json"]))
        lock_pairs = PIN.findall(raw["06-CANDIDATE-WHEELS.txt"].decode("utf-8"))
        locked = {_name(name): version for name, version in lock_pairs}
        if len(direct) != 10 or len(locked) != len(lock_pairs) or locked != metadata:
            raise AdmissionError("package_snapshot_incomplete")
        if set(direct) - set(locked) != {"jieba"} or any(locked[name] != version for name, version in direct.items() if name in locked):
            raise AdmissionError("package_resolution_mismatch")
        for section in re.split(r"(?m)(?=^[A-Za-z0-9][A-Za-z0-9._-]*==)", raw["06-CANDIDATE-WHEELS.txt"].decode("utf-8"))[1:]:
            if not re.search(r"--hash=sha256:[0-9a-f]{64}(?:\s|$)", section):
                raise AdmissionError("package_hash_missing")
        jieba = next(row for row in source["selected_package_candidates"] if _name(row["name"]) == "jieba")
        if not any(f.get("type") == "sdist" and SHA256.fullmatch(f.get("sha256", "")) and f.get("bytes", 0) > 0 for f in jieba["files"]):
            raise AdmissionError("source_archive_hash_missing")
        _scan(_json(raw["06-PACKAGE-SCAN.json"]), direct)
        scans = _scan(_json(raw["06-TRANSITIVE-SCAN.json"]), locked)
        limits = _json(raw["06-LIVE-LIMITS.json"])
        if set(limits) != LIMIT_KEYS or any(type(v) is not int or v <= 0 for v in limits.values()):
            raise AdmissionError("live_limits_invalid")
        models = {"deepdoc": source["deepdoc"]["revision"], "asr": source["asr_model"]["revision"]}
        if any(not REVISION.fullmatch(v) for v in models.values()):
            raise AdmissionError("model_revision_invalid")
        weights = {f["rfilename"]: f for f in source["deepdoc"]["files"]}
        required = {"det.onnx", "rec.onnx", "layout.onnx", "tsr.onnx"}
        if not required <= set(weights):
            raise AdmissionError("model_weights_missing")
        for name in required:
            _weight(weights[name])
        dictionary = source["deepdoc"]["ocr_dictionary"]
        if not SHA256.fullmatch(dictionary.get("sha256", "")) or dictionary.get("bytes", 0) <= 0:
            raise AdmissionError("model_dictionary_manifest_invalid")
        asr_files = source["asr_model"]["files"]
        _weight(next(f for f in asr_files if f["rfilename"] == "model.bin"))
        model_bytes = {
            "deepdoc": sum(weights[n]["size"] for n in required) + dictionary["bytes"],
            "asr": sum(f["size"] for f in asr_files),
        }
    except (KeyError, TypeError, AttributeError, StopIteration):
        raise AdmissionError("audit_shape_invalid") from None
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "audit_digest": digest,
        "file_hashes": hashes,
        "direct_candidates": len(direct),
        "resolved_wheel_packages": len(locked),
        "packages": dict(sorted({**locked, **direct}.items())),
        "models": models,
        "model_metadata_bytes": model_bytes,
        "scan_counts": dict(scans),
        "limits": limits,
    }


def validate_approval(record: dict[str, Any], report: dict[str, Any]) -> None:
    """Validate a human-attributed record for this exact packet; never create consent."""
    if not isinstance(record, dict) or record.get("status") != "approved":
        raise AdmissionError("approval_pending")
    response = record.get("human_response")
    if record.get("decision_source") != "user" or not isinstance(response, str) or not response.strip():
        raise AdmissionError("human_decision_missing")
    try:
        approved_at = datetime.fromisoformat(record.get("approved_at", ""))
    except (ValueError, TypeError):
        raise AdmissionError("decision_time_missing") from None
    if approved_at.tzinfo is None:
        raise AdmissionError("decision_time_missing")
    if record.get("audit_digest") != report["audit_digest"]:
        raise AdmissionError("approved_snapshot_changed")
    for field in ("packages", "models", "limits"):
        if not isinstance(record.get(field), dict) or record[field] != report[field]:
            raise AdmissionError("approved_scope_mismatch")
    if any(type(value) is not int for value in record["limits"].values()):
        raise AdmissionError("approved_limits_invalid")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase-dir", type=Path, default=PHASE)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--audit-only", action="store_true")
    mode.add_argument("--check-approval", action="store_true")
    args = parser.parse_args()
    try:
        report = audit_packet(args.phase_dir)
        if args.check_approval:
            validate_approval(_json(_read(args.phase_dir / "06-APPROVAL.json")), report)
        print(json.dumps({"mode": "approval" if args.check_approval else "audit", "result": "pass", **report}, indent=2))
    except AdmissionError as exc:
        print(json.dumps({"result": "refused", "reason": str(exc)}))
        return 2
    except OSError:
        print(json.dumps({"result": "refused", "reason": "audit_file_unavailable"}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
