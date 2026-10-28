"""Explicit seven-class adapter for the pinned TSR artifact and bounded cell reconstruction.

Tensor preprocessing was cross-checked against InfiniFlow's Apache-2.0 reference
recognizer, commit6677f14bdff0e80b29ec94378ebd02a9c4ef8d54. No upstream code,
constructor or runtime acquisition path is imported.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from deepdoc.geometry import iou
from deepdoc.model_runtime import NativeError
from rag.parsers.tables import Table, TableCell  # noqa: F401 - shared public value types

LABELS = ("table", "table column", "table row", "table column header", "table projected row header", "table spanning cell", "table grid cell")
SCORE_THRESHOLD = 0.2
IOU_THRESHOLD = 0.2


@dataclass(frozen=True)
class StructureRegion:
    label_id: int
    score: float
    box: tuple[float, float, float, float]

    def __post_init__(self):
        if type(self.label_id) is not int or not 0 <= self.label_id < len(LABELS):
            raise NativeError("table_unsupported_label", 502)
        if (
            len(self.box) != 4
            or any(not math.isfinite(v) for v in (*self.box, self.score))
            or not 0 <= self.score <= 1
            or min(self.box) < 0
            or self.box[0] >= self.box[2]
            or self.box[1] >= self.box[3]
        ):
            raise NativeError("invalid_native_result", 502)


class Tables:
    def __init__(self, runtime):
        self.runtime = runtime

    def detect(self, image, page_size=None) -> list[StructureRegion]:
        import numpy as np
        from PIL import Image

        if image.width * image.height > 40_000_000:
            raise NativeError("image_too_large", 413)
        width, height = page_size or image.size
        tensor = np.asarray(image.convert("RGB").resize((640, 640), Image.Resampling.BILINEAR), dtype=np.float32).transpose(2, 0, 1)[None] / 255
        session = self.runtime.session("tsr.onnx")
        output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
        if output.shape != (1, 11, 8400) or not np.isfinite(output).all():
            raise NativeError("model_signature_invalid", 503)
        candidates = []
        for raw in output[0].T:
            label = int(np.argmax(raw[4:]))
            score = float(raw[4 + label])
            if not 0 <= score <= 1:
                raise NativeError("invalid_native_result", 502)
            if score < float(np.float32(SCORE_THRESHOLD)):
                continue
            cx, cy, bw, bh = map(float, raw[:4])
            box = (max(0, (cx - bw / 2) / 640 * width), max(0, (cy - bh / 2) / 640 * height), min(width, (cx + bw / 2) / 640 * width), min(height, (cy + bh / 2) / 640 * height))
            if box[0] >= box[2] or box[1] >= box[3]:
                continue
            candidates.append(StructureRegion(label, score, box))
        kept = []
        for region in sorted(candidates, key=lambda r: (-r.score, r.label_id, r.box)):
            if not any(other.label_id == region.label_id and iou(other.box, region.box) >= IOU_THRESHOLD for other in kept):
                kept.append(region)
            if len(kept) > 4096:
                raise NativeError("output_too_large", 413)
        return sorted(kept, key=lambda r: (r.label_id, r.box[1], r.box[0]))


@dataclass(frozen=True)
class TextToken:
    text: str
    box: tuple[float, float, float, float]

    def __post_init__(self):
        if not isinstance(self.text, str) or len(self.text) > 4096 or len(self.box) != 4 or any(not math.isfinite(v) for v in self.box) or self.box[0] >= self.box[2] or self.box[1] >= self.box[3]:
            raise NativeError("invalid_native_result", 502)


@dataclass(frozen=True)
class TableGrid:
    rows: tuple[float, ...]
    columns: tuple[float, ...]
    # Separators present between adjacent cells, indexed by logical row/column.
    vertical: tuple[tuple[bool, ...], ...]
    horizontal: tuple[tuple[bool, ...], ...]


def pixel_grid(image, regions, page_size) -> TableGrid | None:
    """Use observed rules to refine model anchors, including missing border-defined header rows."""
    import numpy as np

    dark = np.asarray(image.convert("L")) < 128

    def centres(projection):
        groups = []
        for value in np.flatnonzero(projection).tolist():
            if not groups or value > groups[-1][-1] + 2:
                groups.append([value])
            else:
                groups[-1].append(value)
        return [sum(group) / len(group) for group in groups]

    ys = centres(dark.sum(axis=1) >= image.width * 0.45)
    xs = centres(dark.sum(axis=0) >= image.height * 0.55)
    model_columns = sorted([r for r in regions if r.label_id == 1], key=lambda r: r.box[0])
    model_rows = sorted([r for r in regions if r.label_id == 2], key=lambda r: r.box[1])
    if not 2 <= len(ys) <= 257 or not 2 <= len(xs) <= 129 or len(xs) - 1 != len(model_columns) or len(model_rows) < 2:
        return None
    width, height = page_size
    x_units = [x / image.width * width for x in xs]
    y_units = [y / image.height * height for y in ys]
    if any(not x_units[i] < (r.box[0] + r.box[2]) / 2 < x_units[i + 1] for i, r in enumerate(model_columns)):
        return None
    # Model anchors must agree with the observed grid; rules cannot invent a table by themselves.
    if any(not y_units[0] < (r.box[1] + r.box[3]) / 2 < y_units[-1] for r in model_rows):
        return None
    assigned_rows = [next(i for i in range(len(y_units) - 1) if y_units[i] <= (r.box[1] + r.box[3]) / 2 < y_units[i + 1]) for r in model_rows]
    if len(set(assigned_rows)) != len(model_rows):
        return None  # Partial rules must not collapse distinct detected rows/spans.
    vertical = []
    for row in range(len(ys) - 1):
        top, bottom = round(ys[row] + 5), round(ys[row + 1] - 5)
        vertical.append(tuple(bool(dark[max(0, top) : max(top + 1, bottom), max(0, round(x) - 2) : round(x) + 3].mean() > 0.25) for x in xs[1:-1]))
    horizontal = []
    for y in ys[1:-1]:
        horizontal.append(tuple(bool(dark[max(0, round(y) - 2) : round(y) + 3, round(xs[col] + 5) : max(round(xs[col] + 6), round(xs[col + 1] - 5))].mean() > 0.25) for col in range(len(xs) - 1)))
    return TableGrid(tuple(y_units), tuple(x_units), tuple(vertical), tuple(horizontal))


def reconstruct(regions: list[StructureRegion], tokens: list[TextToken], *, grid: TableGrid | None = None) -> Table:
    rows = sorted([r for r in regions if r.label_id == 2], key=lambda r: (r.box[1] + r.box[3]) / 2)
    columns = sorted([r for r in regions if r.label_id == 1], key=lambda r: (r.box[0] + r.box[2]) / 2)
    if not rows or not columns or len(tokens) > 20000:
        raise NativeError("table_structure_unavailable", 502)

    def boundaries(values, low, high):
        return tuple([getattr(values[0], "box")[low], *[(a.box[high] + b.box[low]) / 2 for a, b in zip(values, values[1:])], values[-1].box[high]])

    row_cuts = grid.rows if grid else boundaries(rows, 1, 3)
    col_cuts = grid.columns if grid else boundaries(columns, 0, 2)
    nr, nc = len(row_cuts) - 1, len(col_cuts) - 1
    if nr * nc > 4096 or any(a >= b for a, b in zip(row_cuts, row_cuts[1:])) or any(a >= b for a, b in zip(col_cuts, col_cuts[1:])):
        raise NativeError("table_structure_unavailable", 502)
    parent = {(r, c): (r, c) for r in range(nr) for c in range(nc)}

    def root(p):
        while parent[p] != p:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p

    def join(a, b):
        parent[root(b)] = root(a)

    if grid:
        if len(grid.vertical) != nr or len(grid.horizontal) != nr - 1 or any(len(row) != nc - 1 for row in grid.vertical) or any(len(row) != nc for row in grid.horizontal):
            raise NativeError("table_structure_unavailable", 502)
        for r in range(nr):
            for c in range(nc - 1):
                if not grid.vertical[r][c]:
                    join((r, c), (r, c + 1))
        for r in range(nr - 1):
            for c in range(nc):
                if not grid.horizontal[r][c]:
                    join((r, c), (r + 1, c))
    else:
        for span in sorted([r for r in regions if r.label_id in {5, 6}], key=lambda r: -r.score):
            covered = [
                (r, c) for r in range(nr) for c in range(nc) if span.box[0] <= (col_cuts[c] + col_cuts[c + 1]) / 2 <= span.box[2] and span.box[1] <= (row_cuts[r] + row_cuts[r + 1]) / 2 <= span.box[3]
            ]
            for p in covered[1:]:
                join(covered[0], p)
    groups = {}
    for p in parent:
        groups.setdefault(root(p), []).append(p)
    cells = []
    headers = [r.box for r in regions if r.label_id == 3]
    projected = [r.box for r in regions if r.label_id == 4]
    for positions in sorted(groups.values(), key=min):
        r0, c0 = min(p[0] for p in positions), min(p[1] for p in positions)
        r1, c1 = max(p[0] for p in positions) + 1, max(p[1] for p in positions) + 1
        if len(positions) != (r1 - r0) * (c1 - c0):
            raise NativeError("table_structure_unavailable", 502)
        box = (col_cuts[c0], row_cuts[r0], col_cuts[c1], row_cuts[r1])
        contained = [t for t in tokens if box[0] <= (t.box[0] + t.box[2]) / 2 < box[2] and box[1] <= (t.box[1] + t.box[3]) / 2 < box[3]]
        contained.sort(key=lambda t: (round((t.box[1] + t.box[3]) / 2 / 4), t.box[0]))

        def inside_region(b):
            return b[0] <= (box[0] + box[2]) / 2 <= b[2] and b[1] <= (box[1] + box[3]) / 2 <= b[3]

        header = any(inside_region(b) for b in [*headers, *projected])
        if r0 == 0 and c1 - c0 == nc and any(b[1] > box[1] for b in headers):
            header = True
        cells.append(TableCell(r0, c0, " ".join(t.text for t in contained), r1 - r0, c1 - c0, header))
    return Table(nr, nc, tuple(cells))


def parse_table(runtime, image, tokens, *, page_size=None, caption="") -> Table:
    size = page_size or image.size
    regions = Tables(runtime).detect(image, size)
    made = reconstruct(regions, tokens, grid=pixel_grid(image, regions, size))
    from dataclasses import replace

    return replace(made, caption=caption[:1024])
