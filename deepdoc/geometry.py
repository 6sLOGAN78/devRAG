"""Pure page-unit geometry and canonical layout semantics, without native imports."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from deepdoc.model_runtime import NativeError
from rag.parsers.types import LAYOUT_LABELS, ParsedBlock

LABELS = LAYOUT_LABELS
Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Region:
    label_id: int
    score: float
    box: Box

    def __post_init__(self):
        if type(self.label_id) is not int or not 0 <= self.label_id < len(LABELS):
            raise NativeError("layout_unsupported_label", 502)
        if (
            len(self.box) != 4
            or any(not math.isfinite(x) for x in (*self.box, self.score))
            or not 0 <= self.score <= 1
            or min(self.box) < 0
            or self.box[0] >= self.box[2]
            or self.box[1] >= self.box[3]
        ):
            raise NativeError("invalid_native_result", 502)


def area(box: Box) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def intersection(a: Box, b: Box) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def overlap_ratio(text_box: Box, region: Box) -> float:
    return intersection(text_box, region) / area(text_box) if area(text_box) else 0.0


def iou(a: Box, b: Box) -> float:
    intersect = intersection(a, b)
    union = area(a) + area(b) - intersect
    return intersect / union if union else 0.0


def nms(regions: list[Region], threshold: float = 0.45) -> list[Region]:
    kept: list[Region] = []
    for region in sorted(regions, key=lambda r: (-r.score, r.label_id, r.box)):
        if not any(region.label_id == old.label_id and iou(region.box, old.box) > threshold for old in kept):
            kept.append(region)
    return kept


def _box(block: ParsedBlock) -> Box:
    box = block.boxes[0]
    return box.x0, box.top, box.x1, box.bottom


def _reading_order(blocks: list[ParsedBlock]) -> list[ParsedBlock]:
    result: list[ParsedBlock] = []
    pending = [(blocks, False)]
    while pending:
        group, ordered = pending.pop()
        if ordered or len(group) < 2:
            result.extend(group)
            continue
        # Whitespace gutters split columns; full-width headings separate bands.
        # Use an explicit stack so many sections cannot exhaust Python recursion.
        left, right = min(_box(b)[0] for b in group), max(_box(b)[2] for b in group)
        wide = [b for b in group if b.kind in {"heading", "table"} and _box(b)[2] - _box(b)[0] > (right - left) * 0.65]
        if wide:
            separator = min(wide, key=lambda b: (_box(b)[1], _box(b)[0], b.text))
            middle = (_box(separator)[1] + _box(separator)[3]) / 2
            before = [b for b in group if b is not separator and (_box(b)[1] + _box(b)[3]) / 2 < middle]
            after = [b for b in group if b is not separator and (_box(b)[1] + _box(b)[3]) / 2 >= middle]
            pending.extend([(after, False), ([separator], True), (before, False)])
            continue
        intervals = sorted((_box(b)[0], _box(b)[2]) for b in group)
        end = intervals[0][1]
        gaps = []
        for start, stop in intervals[1:]:
            if start - end >= max(12, (right - left) * 0.03):
                gaps.append((start - end, (start + end) / 2))
            end = max(end, stop)
        if gaps:
            cut = max(gaps)[1]
            before = [b for b in group if (_box(b)[0] + _box(b)[2]) / 2 < cut]
            after = [b for b in group if (_box(b)[0] + _box(b)[2]) / 2 >= cut]
            if before and after:
                pending.extend([(after, False), (before, False)])
                continue
        height = sum(_box(b)[3] - _box(b)[1] for b in group) / len(group) / 2
        result.extend(sorted(group, key=lambda b: (round(_box(b)[1] / max(height, 1)), _box(b)[0], _box(b)[1], b.text)))
    return result


def apply_layout(blocks: list[ParsedBlock], regions: list[Region]) -> list[ParsedBlock]:
    positioned: dict[int, list[ParsedBlock]] = {}
    unpositioned = []
    for block in blocks:
        if not block.boxes:
            unpositioned.append(block)
            continue
        box = _box(block)
        matches = [r for r in regions if r.label_id and overlap_ratio(box, r.box) >= 0.4]
        region = min(matches, key=lambda r: (-overlap_ratio(box, r.box), -r.score, r.label_id, r.box)) if matches else None
        label = LABELS[region.label_id] if region else None
        if label in {"Header", "Footer"}:
            continue
        kind = "heading" if label == "Title" else "table" if label == "Table" else block.kind
        positioned.setdefault(block.boxes[0].page, []).append(replace(block, kind=kind, layout_label=label))
    return [b for page in sorted(positioned) for b in _reading_order(positioned[page])] + unpositioned
