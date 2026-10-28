"""Original two-page table PDF; explicit source geometry and planted cell annotations."""

from __future__ import annotations


def original_table_pdf() -> bytes:
    def stream(lines):
        content = "\n".join(lines).encode("ascii")
        return b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"

    def page_content(page):
        def text(x, top, value, size=13):
            escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            return f"BT /F1 {size} Tf {x} {400 - top} Td ({escaped}) Tj ET"

        lines = ["0.8 w", "0.93 g 60 260 480 50 re f 0 g"]
        # Top-left source table box: (60,90)-(540,340); header spans all three columns.
        for top in [90, 140, 190, 240, 290, 340]:
            lines.append(f"60 {400 - top} m 540 {400 - top} l S")
        for x in [60, 540]:
            lines.append(f"{x} 60 m {x} 310 l S")
        for x in [260, 400]:
            lines.append(f"{x} 60 m {x} 260 l S")
        lines += [text(60, 55, f"Table {page}. Orchard field measurements", 15), text(175, 122, "ORCHARD MEASUREMENTS", 15)]
        for x, value in zip([75, 280, 415], ["Metric", "Recorded", "Unit"]):
            lines.append(text(x, 172, value))
        rows = [("Harvest", "9100", "kg"), ("Height", "52", "m"), ("<b>Literal</b>", "73", "")] if page == 1 else [("Harvest", "281", "kg"), ("Height", "73", "m"), ("<b>Literal</b>", "52", "")]
        for top, row in zip([222, 272, 322], rows):
            for x, value in zip([75, 280, 415], row):
                if value:
                    lines.append(text(x, top, value))
        return stream(lines)

    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [4 0 R 6 0 R] /Count 2 >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for page, page_obj, content_obj in [(1, 4, 5), (2, 6, 7)]:
        objects[page_obj] = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 400] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>".encode()
        objects[content_obj] = page_content(page)
    data = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number, content in sorted(objects.items()):
        offsets[number] = len(data)
        data.extend(f"{number} 0 obj\n".encode() + content + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for number in range(1, len(objects) + 1):
        data.extend(f"{offsets[number]:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(data)
