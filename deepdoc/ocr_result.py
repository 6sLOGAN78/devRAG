"""Pure validation of bounded native OCR results."""

import math
from typing import Any
from deepdoc.model_runtime import NativeError


def validate_result(result: dict[str, Any]) -> None:
    if set(result) != {"schema_version", "width", "height", "spans"} or result["schema_version"] != 1:
        raise NativeError("invalid_native_result", 502)
    width, height = result["width"], result["height"]
    if type(width) is not int or type(height) is not int or min(width, height) < 1 or width * height > 40_000_000:
        raise NativeError("invalid_native_result", 502)
    if not isinstance(result["spans"], list) or len(result["spans"]) > 1000:
        raise NativeError("invalid_native_result", 502)
    for span in result["spans"]:
        if not isinstance(span, dict) or set(span) != {"text", "confidence", "box"}:
            raise NativeError("invalid_native_result", 502)
        if not isinstance(span["text"], str) or len(span["text"]) > 8192:
            raise NativeError("invalid_native_result", 502)
        box = span["box"]
        numbers = [span["confidence"], *box] if isinstance(box, list) and len(box) == 4 else []
        if len(numbers) != 5 or any(type(n) not in (int, float) or not math.isfinite(n) for n in numbers):
            raise NativeError("invalid_native_result", 502)
        x0, y0, x1, y1 = box
        if not (0 <= span["confidence"] <= 1 and 0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise NativeError("invalid_native_result", 502)
