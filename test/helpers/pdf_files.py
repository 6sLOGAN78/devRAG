"""Hand-written valid PDFs for parser tests (plan 04-08, D-16). Pure byte assembly, no PDF package."""
from __future__ import annotations

from collections.abc import Sequence

Page = Sequence[str] | None


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _content(lines: Sequence[str], height: float, font_size: int) -> bytes:
    ops = ["BT", f"/F1 {font_size} Tf", "16 TL", f"72 {height - 72:g} Td"]
    for line in lines:
        ops.append(f"({_escape(line)}) Tj T*")
    ops.append("ET")
    return "\n".join(ops).encode("latin-1")


def text_pdf(
    pages: Sequence[Page],
    *,
    mediabox: tuple[float, float, float, float] = (0, 0, 595, 842),
    rotations: dict[int, int] | None = None,
    cropbox: tuple[float, float, float, float] | None = None,
    font_size: int = 12,
) -> bytes:
    """Bytes of a valid PDF. A page is a list of text lines (top-down from y = height - 72) or None for no content stream."""
    rotations = rotations or {}
    n = len(pages)
    # object numbers: 1 catalog, 2 pages, 3 font, then per page: page object, optional content object
    objects: dict[int, bytes] = {}
    kids: list[int] = []
    next_id = 4
    height = mediabox[3]
    for i, page in enumerate(pages):
        page_id = next_id
        next_id += 1
        kids.append(page_id)
        extra = ""
        if page is not None:
            content_id = next_id
            next_id += 1
            stream = _content(page, height, font_size)
            objects[content_id] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
            extra += f" /Contents {content_id} 0 R"
        if i in rotations:
            extra += f" /Rotate {rotations[i]}"
        if cropbox is not None:
            extra += " /CropBox [" + " ".join(f"{v:g}" for v in cropbox) + "]"
        mb = " ".join(f"{v:g}" for v in mediabox)
        objects[page_id] = f"<< /Type /Page /Parent 2 0 R /MediaBox [{mb}] /Resources << /Font << /F1 3 0 R >> >>{extra} >>".encode()
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {n} >>".encode()
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for oid in sorted(objects):
        offsets[oid] = len(out)
        out += b"%d 0 obj\n" % oid + objects[oid] + b"\nendobj\n"
    xref = len(out)
    size = max(objects) + 1
    out += b"xref\n0 %d\n" % size + b"0000000000 65535 f \n"
    for oid in range(1, size):
        out += b"%010d 00000 n \n" % offsets[oid]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref)
    return bytes(out)


def thirteen_page_pdf() -> bytes:
    return text_pdf([[f"Page {p} line {k} alpha" for k in range(1, 7)] for p in range(1, 14)])


def garbage_bytes() -> bytes:
    return b"this is not a pdf at all, just bytes " * 20


def truncated(data: bytes, keep: float = 0.5) -> bytes:
    return data[: int(len(data) * keep)]
