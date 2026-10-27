"""Bounded deterministic PNG normalization, inside the isolated native process only."""

from __future__ import annotations

import io
import warnings

from deepdoc.model_runtime import NativeError
from rag.parsers.assets import MAX_ASSET_BYTES, MAX_ASSET_PIXELS, ParsedAsset


def normalize_image(content: bytes) -> ParsedAsset:
    from PIL import Image, ImageOps

    if len(content) > 16 * 1024 * 1024:
        raise NativeError("image_too_large", 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in {"PNG", "JPEG"} or getattr(image, "n_frames", 1) != 1:
                    raise NativeError("invalid_image")
                if image.width * image.height > MAX_ASSET_PIXELS:
                    raise NativeError("image_too_large", 413)
                oriented = ImageOps.exif_transpose(image)
                mode = "RGBA" if "A" in oriented.getbands() or "transparency" in image.info else "RGB"
                normalized = oriented.convert(mode)
                buffer = io.BytesIO()
                normalized.save(buffer, "PNG", optimize=False, compress_level=6)
                data = buffer.getvalue()
                if len(data) > MAX_ASSET_BYTES:
                    raise NativeError("image_too_large", 413)
                return ParsedAsset.from_png(data, width=normalized.width, height=normalized.height)
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise NativeError("invalid_image") from None
