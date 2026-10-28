"""CPU DBNet detection and CRNN/CTC recognition over locally verified ONNX assets."""

from __future__ import annotations

import io
import math
import warnings
from typing import Any

from deepdoc.model_runtime import ModelRuntime, NativeError


def decode_ctc(indices: list[int], scores: list[float], alphabet: list[str]) -> tuple[str, float]:
    text, confidence, previous = [], [], -1
    for index, score in zip(indices, scores, strict=True):
        if not 0 <= index < len(alphabet) or not math.isfinite(score):
            raise NativeError("model_signature_invalid", 503)
        if index and index != previous:
            text.append(alphabet[index])
            confidence.append(score)
        previous = index
    return "".join(text), sum(confidence) / len(confidence) if confidence else 0.0


def decode_image(content: bytes, *, max_pixels: int = 40_000_000):
    import cv2
    import numpy as np
    from PIL import Image

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as header:
                width, height = header.size
                if width * height > max_pixels or min(width, height) < 1:
                    raise NativeError("image_too_large", 413)
                if header.format not in {"PNG", "JPEG"} or getattr(header, "n_frames", 1) != 1:
                    raise NativeError("invalid_image")
        image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        if image is None or image.shape[:2] != (height, width):
            raise NativeError("invalid_image")
        return image
    except (OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise NativeError("invalid_image") from None


def _ordered_points(points):
    import numpy as np

    ordered = np.empty((4, 2), dtype=np.float32)
    sums, differences = points.sum(axis=1), np.diff(points, axis=1).ravel()
    ordered[0], ordered[2] = points[sums.argmin()], points[sums.argmax()]
    ordered[1], ordered[3] = points[differences.argmin()], points[differences.argmax()]
    return ordered


def _crop(image, points):
    import cv2
    import numpy as np

    points = _ordered_points(points)
    width = max(1, round(max(np.linalg.norm(points[0] - points[1]), np.linalg.norm(points[2] - points[3]))))
    height = max(1, round(max(np.linalg.norm(points[0] - points[3]), np.linalg.norm(points[1] - points[2]))))
    target = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32)
    transform = cv2.getPerspectiveTransform(points, target)
    crop = cv2.warpPerspective(image, transform, (width, height), borderMode=cv2.BORDER_REPLICATE)
    return np.rot90(crop) if height / width >= 1.5 else crop


def word_spans(active: list[int], ink_height: int) -> list[tuple[int, int]]:
    """Separate visible whitespace, never infer or rewrite the recognized text."""
    if not active:
        return []
    threshold = max(3, ink_height * 0.35)
    starts, ends = [active[0]], []
    for previous, current in zip(active, active[1:]):
        if current - previous - 1 > threshold:
            ends.append(previous + 1)
            starts.append(current)
    ends.append(active[-1] + 1)
    return list(zip(starts, ends, strict=True))


class OCR:
    def __init__(self, runtime: ModelRuntime):
        self.runtime = runtime

    def _detect(self, image):
        import cv2
        import numpy as np
        import pyclipper
        from shapely.geometry import Polygon

        height, width = image.shape[:2]
        ratio = min(1.0, 960 / max(height, width))
        resized_h, resized_w = (max(32, round(value * ratio / 32) * 32) for value in (height, width))
        resized = cv2.resize(image, (resized_w, resized_h)).astype(np.float32) / 255
        normalized = (resized - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
        tensor = np.ascontiguousarray(normalized.transpose(2, 0, 1)[None])
        session = self.runtime.session("det.onnx")
        probabilities = session.run(None, {session.get_inputs()[0].name: tensor})[0]
        if probabilities.ndim != 4 or not np.isfinite(probabilities).all():
            raise NativeError("model_signature_invalid", 503)
        scores = probabilities[0, 0]
        contours, _ = cv2.findContours((scores > 0.3).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:1000]:
            rectangle = cv2.minAreaRect(contour)
            if min(rectangle[1]) < 3:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(mask, [contour - np.array([[[x, y]]])], 1)
            if cv2.mean(scores[y : y + h, x : x + w], mask)[0] < 0.5:
                continue
            points = cv2.boxPoints(rectangle)
            polygon = Polygon(points)
            if polygon.length <= 0 or polygon.area <= 0:
                continue
            offset = pyclipper.PyclipperOffset()
            offset.AddPath(np.rint(points).astype(int).tolist(), pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
            expanded = offset.Execute(polygon.area * 1.5 / polygon.length)
            if len(expanded) != 1:
                continue
            points = cv2.boxPoints(cv2.minAreaRect(np.asarray(expanded[0], dtype=np.float32)))
            points[:, 0] = np.clip(points[:, 0] * width / scores.shape[1], 0, width - 1)
            points[:, 1] = np.clip(points[:, 1] * height / scores.shape[0], 0, height - 1)
            if np.ptp(points[:, 0]) >= 3 and np.ptp(points[:, 1]) >= 3:
                boxes.append(points)
        return sorted(boxes, key=lambda box: (round(float(box[:, 1].min()) / 10), float(box[:, 0].min())))

    def _recognize(self, image) -> tuple[str, float]:
        import cv2
        import numpy as np

        session = self.runtime.session("rec.onnx")
        shape = session.get_inputs()[0].shape
        image_h = shape[2] if isinstance(shape[2], int) else 48
        image_w = shape[3] if isinstance(shape[3], int) else min(4096, max(320, math.ceil(image_h * image.shape[1] / image.shape[0])))
        scaled_w = min(image_w, math.ceil(image_h * image.shape[1] / image.shape[0]))
        resized = cv2.resize(image, (scaled_w, image_h)).astype(np.float32) / 127.5 - 1
        tensor = np.zeros((1, 3, image_h, image_w), dtype=np.float32)
        tensor[0, :, :, :scaled_w] = resized.transpose(2, 0, 1)
        output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
        if output.ndim != 3 or output.shape[0] != 1 or output.shape[2] != len(self.runtime.alphabet):
            raise NativeError("model_signature_invalid", 503)
        if not np.isfinite(output).all():
            raise NativeError("model_signature_invalid", 503)
        indices, confidence = output[0].argmax(axis=1), output[0].max(axis=1)
        return decode_ctc(indices.tolist(), confidence.tolist(), self.runtime.alphabet)

    def ocr(self, content: bytes) -> dict[str, Any]:
        import cv2
        import numpy as np

        image = decode_image(content)
        spans = []
        recognized_words = 0
        for points in self._detect(image):
            crop = _crop(image, points)
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
            rows = np.flatnonzero(np.any(ink > 0, axis=1))
            if not rows.size:
                continue
            columns = np.flatnonzero(np.any(ink > 0, axis=0))
            words = word_spans(columns.tolist(), int(rows[-1] - rows[0] + 1))
            recognized_words += len(words)
            if recognized_words > 1000:
                raise NativeError("too_many_text_regions", 413)
            recognized = [self._recognize(crop[:, max(0, left - 2) : min(crop.shape[1], right + 2)]) for left, right in words]
            text = " ".join(word for word, _ in recognized)
            confidence = min((score for _, score in recognized), default=0.0)
            if not text.strip() or confidence < 0.5:
                continue
            spans.append(
                {"text": text, "confidence": min(1.0, max(0.0, confidence)), "box": [float(points[:, 0].min()), float(points[:, 1].min()), float(points[:, 0].max()), float(points[:, 1].max())]}
            )
        return {"schema_version": 1, "width": image.shape[1], "height": image.shape[0], "spans": spans}
