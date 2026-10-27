"""Local, hash-verified CPU model loading; no download or model-code execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class NativeError(Exception):
    """Fixed protocol failure with no source text, file path or operator secret."""

    def __init__(self, code: str, status: int = 400):
        self.code, self.status = code, status
        super().__init__(code)


def verify_file(path: Path, digest: str, size: int) -> None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
            raise NativeError("model_unavailable", 503)
        checksum = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                checksum.update(chunk)
        if checksum.hexdigest() != digest:
            raise NativeError("model_unavailable", 503)
    except OSError:
        raise NativeError("model_unavailable", 503) from None


class ModelRuntime:
    def __init__(self, directory: Path):
        self.directory = directory
        manifest = json.loads(Path(__file__).with_name("models.json").read_text())
        self.revision = manifest["revision"]
        self.artifacts = manifest["files"]
        self.sessions: dict[str, Any] = {}
        for name, item in self.artifacts.items():
            verify_file(directory / name, item["sha256"], item["bytes"])
        self.alphabet = ["", *(directory / "ocr.res").read_text().splitlines(), " "]
        self.session("det.onnx")
        self.session("rec.onnx")

    def session(self, name: str):
        if name not in self.artifacts or not name.endswith(".onnx"):
            raise NativeError("model_unavailable", 503)
        if name not in self.sessions:
            import onnxruntime as ort

            item = self.artifacts[name]
            verify_file(self.directory / name, item["sha256"], item["bytes"])
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            options.enable_cpu_mem_arena = False
            try:
                session = ort.InferenceSession(str(self.directory / name), sess_options=options,
                                               providers=["CPUExecutionProvider"])
                if len(session.get_inputs()) != 1:
                    raise NativeError("model_signature_invalid", 503)
                self.sessions[name] = session
            except Exception:
                raise NativeError("model_unavailable", 503) from None
        return self.sessions[name]
