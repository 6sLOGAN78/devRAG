"""Explicit adapter for the approved YOLOv10 document-layout artifact."""

from __future__ import annotations

import math

from deepdoc.geometry import Region, nms
from deepdoc.model_runtime import ModelRuntime, NativeError

SCORE_THRESHOLD = 0.08
IOU_THRESHOLD = 0.45
# Canonical spec IDs differ from the ten model-specific classes in ONNX metadata.
MODEL_TO_CANONICAL = {0: 2, 1: 1, 2: 9, 3: 3, 4: 4, 5: 5, 6: 6, 7: 6, 8: 10, 9: 4}


def semantic_id(model_id: int, box, height: float, *, has_body: bool = True) -> int:
    if type(model_id) is not int or model_id not in MODEL_TO_CANONICAL:
        raise NativeError("layout_unsupported_label", 502)
    if model_id == 2 and has_body:
        if box[3] <= height * 0.10:
            return 7
        if box[1] >= height * 0.90:
            return 8
    return MODEL_TO_CANONICAL[model_id]


class Layout:
    def __init__(self, runtime: ModelRuntime):
        self.runtime = runtime

    def detect(self, image, page_size: tuple[float, float]) -> list[Region]:
        import numpy as np
        from PIL import Image

        width, height = image.size
        ratio = min(1024 / width, 1024 / height)
        scaled = (round(width * ratio), round(height * ratio))
        left, top = round((1024 - scaled[0]) / 2 - 0.1), round((1024 - scaled[1]) / 2 - 0.1)
        canvas = Image.new("RGB", (1024, 1024), (114, 114, 114))
        canvas.paste(image.convert("RGB").resize(scaled, Image.Resampling.BILINEAR), (left, top))
        tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
        session = self.runtime.session("layout.onnx")
        output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
        if output.shape != (1, 300, 6):
            raise NativeError("model_signature_invalid", 503)
        detections = []
        page_width, page_height = page_size
        for x0, y0, x1, y1, score, label in output[0].tolist():
            if not all(math.isfinite(v) for v in (x0, y0, x1, y1, score, label)):
                raise NativeError("invalid_native_result", 502)
            if score < float(np.float32(SCORE_THRESHOLD)):
                continue
            if label != int(label):
                raise NativeError("layout_unsupported_label", 502)
            # Undo exact rounded letterbox dimensions, then pixels -> page units once.
            box = (
                max(0, min(page_width, (x0 - left) / scaled[0] * page_width)),
                max(0, min(page_height, (y0 - top) / scaled[1] * page_height)),
                max(0, min(page_width, (x1 - left) / scaled[0] * page_width)),
                max(0, min(page_height, (y1 - top) / scaled[1] * page_height)),
            )
            if box[0] >= box[2] or box[1] >= box[3]:
                continue  # detections wholly in the padding carry no source region
            if int(label) not in MODEL_TO_CANONICAL:
                raise NativeError("layout_unsupported_label", 502)
            detections.append((int(label), score, box))
        # "abandon" is an ambiguous model class. A margin is page furniture only
        # with independent body evidence; an isolated short source stays readable.
        has_body = any(label in {0, 1, 3, 5, 8} and page_height * 0.1 < (box[1] + box[3]) / 2 < page_height * 0.9 for label, _, box in detections)
        regions = [Region(semantic_id(label, box, page_height, has_body=has_body), score, box) for label, score, box in detections]
        return nms(regions, IOU_THRESHOLD)
