"""Original mixed native/scanned PDF fixture, using only a fixed original bitmap and byte assembly."""

import io

from PIL import Image


def mixed_pdf(image_path):
    with Image.open(image_path) as image:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "JPEG", quality=95)
        width, height = image.size
    bitmap = buffer.getvalue()
    native = b"BT /F1 14 Tf 30 120 Td (MIXED NATIVE FACT 73) Tj ET"
    drawing = b"q 700 0 0 200 0 0 cm /Im1 Do Q"
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [4 0 R 6 0 R] /Count 2 >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        4: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 700 200] /Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>",
        5: b"<< /Length %d >>\nstream\n" % len(native) + native + b"\nendstream",
        6: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 700 200] /Resources << /XObject << /Im1 7 0 R >> >> /Contents 8 0 R >>",
        7: f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(bitmap)} >>\nstream\n".encode()
        + bitmap
        + b"\nendstream",
        8: b"<< /Length %d >>\nstream\n" % len(drawing) + drawing + b"\nendstream",
    }
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for oid, body in sorted(objects.items()):
        offsets[oid] = len(out)
        out += f"{oid} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 9\n0000000000 65535 f \n"
    for oid in range(1, 9):
        out += b"%010d 00000 n \n" % offsets[oid]
    out += b"trailer\n<< /Size 9 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref
    return bytes(out)
