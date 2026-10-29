"""Normalize images in DeepDoc; OCR-only mode remains an explicit operation."""

from rag.parsers.types import ParsedBlock, PageBox
from rag.parsers.errors import FileTooLarge, NoReadableText
from rag.parsers.deepdoc_client import DeepDocClient, NativeUnavailable


def parse(source, report, *, page_range=None, limits=None, settings=None, parser_config=None):
    if settings is None or not settings.deepdoc.url:
        raise NativeUnavailable()
    if source.size > 16 * 1024 * 1024:
        raise FileTooLarge()
    with source.path.open("rb") as stream:
        content = stream.read(16 * 1024 * 1024 + 1)
    if len(content) > 16 * 1024 * 1024:
        raise FileTooLarge()
    client = DeepDocClient(settings.deepdoc)
    asset = client.normalize_image(content)
    if not (parser_config or {}).get("picture_ocr_only", False):
        from rag.llm.vision_model import MAX_IMAGE_BYTES

        if len(asset.content) > MAX_IMAGE_BYTES:
            raise FileTooLarge()
    text = ""
    boxes = ()
    sizes = {}
    if (parser_config or {}).get("picture_ocr_only", False):
        result = client.ocr_image(asset.content)
        text = "\n".join(span["text"] for span in result["spans"])
        if not text.strip():
            raise NoReadableText()
        boxes = tuple(PageBox(1, *span["box"]) for span in result["spans"])
        sizes = {1: (result["width"], result["height"])}
    report.pages_total = 1
    return iter([ParsedBlock(text, "image", boxes=boxes, page_sizes=sizes, assets=(asset,))])
