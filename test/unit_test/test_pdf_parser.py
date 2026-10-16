"""PDF parser, rasteriser and thumbnail (plan 04-08)."""
from __future__ import annotations

import threading
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from rag.parsers.errors import FileDamaged
from rag.parsers.pdf import PDFIUM_LOCK, count_pages, parse, rasterize_page, thumbnail_data_url
from rag.parsers.router import parser_for_suffix
from rag.parsers.types import ParseReport, SourceFile
from test.helpers.pdf_files import garbage_bytes, text_pdf, thirteen_page_pdf, truncated

pytestmark = pytest.mark.unit


def _write(tmp_path: Path, data: bytes, name: str = "a.pdf") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _run(path: Path, page_range=None):
    report = ParseReport()
    blocks = list(parse(SourceFile(path, "pdf", path.stat().st_size), report, page_range=page_range))
    return blocks, report


def test_page_count_and_ranges(tmp_path):
    path = _write(tmp_path, thirteen_page_pdf())
    assert count_pages(path) == 13
    first, r1 = _run(path, (0, 12))
    second, r2 = _run(path, (12, 13))
    assert r1.pages_total == 12 and r2.pages_total == 1
    assert {b.boxes[0].page for b in first + second} == set(range(1, 14))
    seven = [b for b in first if b.boxes[0].page == 7]
    assert seven and "Page 7 line 3 alpha" in "\n".join(b.text for b in seven)
    assert all(b.boxes[0].page == 7 for b in seven)


def test_range_is_clamped(tmp_path):
    path = _write(tmp_path, thirteen_page_pdf())
    _, report = _run(path, (10, 99))
    assert report.pages_total == 3


def test_blank_pages_counted(tmp_path):
    lines = ["hello", "world"]
    path = _write(tmp_path, text_pdf([lines, None, lines]))
    blocks, report = _run(path)
    assert report.pages_without_text == 1 and report.pages_total == 3
    assert {b.boxes[0].page for b in blocks} == {1, 3}
    path2 = _write(tmp_path, text_pdf([None, None]), "b.pdf")
    blocks, report = _run(path2)
    assert blocks == [] and report.pages_without_text == report.pages_total == 2


def test_damaged_files(tmp_path):
    good = thirteen_page_pdf()
    for name, data in (("g.pdf", garbage_bytes()), ("t.pdf", truncated(good, 0.4))):
        path = _write(tmp_path, data, name)
        with pytest.raises(FileDamaged) as info:
            _run(path)
        assert str(tmp_path) not in str(info.value) and name not in str(info.value)
    with pytest.raises(FileDamaged):
        count_pages(tmp_path / "missing.pdf")


def test_raster_size_and_thumbnail(tmp_path):
    path = _write(tmp_path, thirteen_page_pdf())
    image = rasterize_page(path, 0)
    assert image.size == (round(595 * 3), round(842 * 3))
    url = thumbnail_data_url(path)
    assert url.startswith("data:image/jpeg;base64,") and len(url) <= 16384


def _ink(image, box, page_size, shift=0.0) -> float:
    w, h = page_size
    x0 = int(box.x0 / w * image.width)
    x1 = max(x0 + 1, int(box.x1 / w * image.width))
    y0 = int((box.top + shift) / h * image.height)
    y1 = max(y0 + 1, int((box.bottom + shift) / h * image.height))
    region = image.convert("L").crop((x0, y0, x1, y1))
    pixels = region.tobytes()
    return sum(1 for p in pixels if p < 128) / len(pixels)


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"rotations": {0: 90}}, {"rotations": {0: 270}}, {"rotations": {0: 180}}, {"cropbox": (50, 200, 500, 842)}],
    ids=["rot0", "rot90", "rot270", "rot180", "cropbox"],
)
def test_box_alignment(tmp_path, kwargs):
    path = _write(tmp_path, text_pdf([["Alignment check line"]], **kwargs))
    blocks, _ = _run(path)
    assert len(blocks) == 1
    block = blocks[0]
    box = block.boxes[0]
    page_size = block.page_sizes[1]
    image = rasterize_page(path, 0, zoom=1)
    assert image.size == (round(page_size[0]), round(page_size[1]))
    assert _ink(image, box, page_size) >= 0.02
    shift = (box.bottom - box.top) + 40
    if box.bottom + shift <= page_size[1]:
        assert _ink(image, box, page_size, shift) == 0.0
    else:
        assert _ink(image, box, page_size, -shift) == 0.0 if box.top - shift >= 0 else True


def test_boxes_and_sizes_inside_page(tmp_path):
    path = _write(tmp_path, text_pdf([["one", "two"]], rotations={0: 90}, cropbox=(50, 200, 500, 842)))
    blocks, _ = _run(path)
    for block in blocks:
        w, h = block.page_sizes[1]
        assert (w, h) == (642.0, 450.0)
        for b in block.boxes:
            assert -1 <= b.x0 <= b.x1 <= w + 1 and -1 <= b.top <= b.bottom <= h + 1


def test_concurrent_parse(tmp_path):
    path = _write(tmp_path, thirteen_page_pdf())
    results: dict[int, int] = {}
    errors: list[BaseException] = []

    def work(slot: int, rng: tuple[int, int]) -> None:
        try:
            results[slot] = len(_run(path, rng)[0])
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(0, (0, 6))), threading.Thread(target=work, args=(1, (6, 13)))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and results[0] > 0 and results[1] > 0


def test_lock_is_reentrant_and_router_loads_module():
    with PDFIUM_LOCK:
        with PDFIUM_LOCK:
            pass
    assert parser_for_suffix("pdf").load().parse is parse
    assert pdfium.PdfDocument(thirteen_page_pdf())


# --- security hardening (post-review): bounded rendering, honoured limits ---------------------------------------------------


def test_huge_mediabox_refused_without_rendering(tmp_path, monkeypatch):
    from rag.parsers.errors import FileTooLarge

    def boom(*args, **kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("render was called for an absurd page")

    monkeypatch.setattr(pdfium.PdfPage, "render", boom)
    path = _write(tmp_path, text_pdf([["x"]], mediabox=(0, 0, 200000, 200000)))
    with pytest.raises(FileTooLarge):
        rasterize_page(path, 0)
    with pytest.raises(FileTooLarge):
        thumbnail_data_url(path)


def test_large_but_legal_page_is_scaled_into_budget(tmp_path):
    from rag.parsers.pdf import MAX_PIXELS, MAX_SIDE

    path = _write(tmp_path, text_pdf([["x"]], mediabox=(0, 0, 14000, 14000)))
    image = rasterize_page(path, 0)
    assert image.width * image.height <= MAX_PIXELS * 1.01
    assert max(image.size) <= MAX_SIDE


def test_thumbnail_scale_follows_target_width(tmp_path, monkeypatch):
    scales: list[float] = []
    real = pdfium.PdfPage.render

    def spy(self, *args, **kwargs):
        scales.append(kwargs.get("scale", args[0] if args else 1))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pdfium.PdfPage, "render", spy)
    path = _write(tmp_path, text_pdf([["x"]], mediabox=(0, 0, 2000, 2000)))
    assert thumbnail_data_url(path).startswith("data:image/jpeg;base64,")
    assert scales and scales[0] < 0.5


def test_page_cap_enforced(tmp_path):
    from rag.parsers.errors import FileTooLarge
    from rag.parsers.types import ParseLimits

    path = _write(tmp_path, thirteen_page_pdf())
    with pytest.raises(FileTooLarge):
        parse(SourceFile(path, "pdf", path.stat().st_size), ParseReport(), limits=ParseLimits(max_pages=12))
    assert ParseLimits().max_pages == 20000
    assert list(parse(SourceFile(path, "pdf", path.stat().st_size), ParseReport(), limits=ParseLimits(max_pages=13)))


def test_max_text_bytes_enforced(tmp_path):
    from rag.parsers.errors import FileTooLarge
    from rag.parsers.types import ParseLimits

    path = _write(tmp_path, thirteen_page_pdf())
    report = ParseReport()
    blocks = parse(SourceFile(path, "pdf", path.stat().st_size), report, limits=ParseLimits(max_text_bytes=100))
    with pytest.raises(FileTooLarge):
        list(blocks)
