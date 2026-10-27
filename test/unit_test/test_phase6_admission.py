"""The acquisition checkpoint stays closed until the exact human-reviewed snapshot is accepted."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from scripts.probe.phase6_admission import AUDIT_FILES, AdmissionError, audit_packet, validate_approval

pytestmark = pytest.mark.unit
PHASE = Path(__file__).resolve().parents[2] / ".planning/phases/06-deep-parsing-and-chunking-breadth"


@pytest.fixture
def packet(tmp_path: Path) -> Path:
    for name in AUDIT_FILES:
        shutil.copyfile(PHASE / name, tmp_path / name)
    return tmp_path


def accepted(report: dict) -> dict:
    """Synthetic test consent only; never written to the real acquisition record."""
    return {
        "status": "approved",
        "decision_source": "user",
        "human_response": "Synthetic fixture: accept the exact audited snapshot and limits.",
        "approved_at": "2026-10-27T00:00:00+00:00",
        "audit_digest": report["audit_digest"],
        "packages": dict(report["packages"]),
        "models": dict(report["models"]),
        "limits": dict(report["limits"]),
    }


def test_complete_current_packet_exposes_acquisition_scope_without_inference(packet: Path) -> None:
    report = audit_packet(packet)
    assert report["direct_candidates"] == 10
    assert report["resolved_wheel_packages"] == 40
    assert len(report["packages"]) == 41  # source-only Jieba is separate from the wheel resolution
    assert report["scan_counts"] == {"OK": 37, "SUS": 3}
    assert set(report["models"]) == {"deepdoc", "asr"}
    assert report["limits"]["cloud_ocr"] == 6


def test_exact_explicit_human_record_can_admit_the_unchanged_packet(packet: Path) -> None:
    report = audit_packet(packet)
    validate_approval(accepted(report), report)


@pytest.mark.parametrize("status", ["pending", "declined", "revise", ""])
def test_pending_or_negative_decisions_cannot_be_treated_as_consent(packet: Path, status: str) -> None:
    report = audit_packet(packet)
    record = accepted(report)
    record["status"] = status
    with pytest.raises(AdmissionError):
        validate_approval(record, report)


@pytest.mark.parametrize("response", ["", " ", "\n"])
def test_approved_flag_without_an_actual_response_is_refused(packet: Path, response: str) -> None:
    report = audit_packet(packet)
    record = accepted(report)
    record["human_response"] = response
    with pytest.raises(AdmissionError):
        validate_approval(record, report)


def test_auto_mode_cannot_supply_human_consent(packet: Path) -> None:
    report = audit_packet(packet)
    record = accepted(report)
    record["decision_source"] = "auto"
    with pytest.raises(AdmissionError):
        validate_approval(record, report)


def test_a_changed_artifact_invalidates_the_previous_acceptance(packet: Path) -> None:
    old = audit_packet(packet)
    record = accepted(old)
    source = packet / "06-SOURCE-EVIDENCE.json"
    source.write_text(source.read_text() + "\n")
    current = audit_packet(packet)
    assert current["audit_digest"] != old["audit_digest"]
    with pytest.raises(AdmissionError):
        validate_approval(record, current)


@pytest.mark.parametrize("kind", ["extra_package", "changed_version", "changed_model", "higher_limit", "missing_package"])
def test_acceptance_cannot_substitute_packages_models_or_limits(packet: Path, kind: str) -> None:
    report = audit_packet(packet)
    record = accepted(report)
    if kind == "extra_package":
        record["packages"]["an-unreviewed-package"] = "1.0"
    elif kind == "changed_version":
        record["packages"]["onnxruntime"] = "999.0"
    elif kind == "changed_model":
        record["models"]["asr"] = "unreviewed-revision"
    elif kind == "higher_limit":
        record["limits"]["vision"] += 1
    else:
        record["packages"].pop("jieba")
    with pytest.raises(AdmissionError):
        validate_approval(record, report)


def test_a_slop_verdict_blocks_the_packet_before_any_install(packet: Path) -> None:
    path = packet / "06-TRANSITIVE-SCAN.json"
    rows = json.loads(path.read_text())
    rows[0]["status"] = "SLOP"
    path.write_text(json.dumps(rows))
    with pytest.raises(AdmissionError):
        audit_packet(packet)


def test_missing_scan_coverage_is_not_assumed_safe(packet: Path) -> None:
    path = packet / "06-PACKAGE-SCAN.json"
    path.write_text(json.dumps(json.loads(path.read_text())[1:]))
    with pytest.raises(AdmissionError):
        audit_packet(packet)


def test_missing_weight_digest_cannot_pass_metadata_audit(packet: Path) -> None:
    path = packet / "06-SOURCE-EVIDENCE.json"
    source = json.loads(path.read_text())
    source = copy.deepcopy(source)
    next(f for f in source["deepdoc"]["files"] if f["rfilename"] == "det.onnx")["lfs"]["sha256"] = ""
    path.write_text(json.dumps(source))
    with pytest.raises(AdmissionError):
        audit_packet(packet)


def test_boolean_cannot_masquerade_as_a_numeric_call_cap(packet: Path) -> None:
    path = packet / "06-LIVE-LIMITS.json"
    limits = json.loads(path.read_text())
    limits["vision"] = True
    path.write_text(json.dumps(limits))
    with pytest.raises(AdmissionError):
        audit_packet(packet)
