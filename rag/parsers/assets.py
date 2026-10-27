"""Typed bounded normalized PNG descriptors; no image decoder or native imports."""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Literal

from rag.parsers.errors import FileDamaged, FileTooLarge

MAX_ASSET_BYTES = 8 * 1024 * 1024
MAX_ASSETS = 128
MAX_ASSET_PIXELS = 40_000_000
_HEX32 = re.compile(r"[0-9a-f]{32}")
_SHA = re.compile(r"[0-9a-f]{64}")
_PNG = b"\x89PNG\r\n\x1a\n"


class InvalidAsset(FileDamaged):
    message = "the normalized image is not valid"


@dataclass(frozen=True)
class ParsedAsset:
    content: bytes
    sha256: str
    width: int
    height: int
    mime_type: Literal["image/png"] = "image/png"
    kind: Literal["image", "table"] = "image"
    caption: str = ""
    page: int | None = None

    def __post_init__(self):
        if type(self.content) is not bytes or len(self.content) > MAX_ASSET_BYTES:
            raise FileTooLarge()
        if not self.content.startswith(_PNG) or self.mime_type != "image/png" or self.kind not in {"image", "table"}:
            raise InvalidAsset()
        if type(self.width) is not int or type(self.height) is not int or min(self.width, self.height) <= 0 or self.width * self.height > MAX_ASSET_PIXELS:
            raise InvalidAsset()
        if not isinstance(self.sha256, str) or _SHA.fullmatch(self.sha256) is None or hashlib.sha256(self.content).hexdigest() != self.sha256:
            raise InvalidAsset()
        if not isinstance(self.caption, str) or len(self.caption) > 1024:
            raise InvalidAsset()
        if self.page is not None and (type(self.page) is not int or not 1 <= self.page <= 1_000_000):
            raise InvalidAsset()

    @classmethod
    def from_png(cls, content: bytes, *, width: int, height: int, caption: str = "", page: int | None = None, kind: Literal["image", "table"] = "image"):
        return cls(content, hashlib.sha256(content).hexdigest(), width, height, caption=caption, page=page, kind=kind)


def encode_asset(asset: ParsedAsset) -> dict:
    data = asdict(asset)
    data.pop("content")
    data["content_base64"] = base64.b64encode(asset.content).decode("ascii")
    return data


def decode_asset(raw: object) -> ParsedAsset:
    if not isinstance(raw, dict) or set(raw) != {"content_base64", "sha256", "width", "height", "mime_type", "kind", "caption", "page"}:
        raise InvalidAsset()
    value = raw["content_base64"]
    if not isinstance(value, str) or len(value) > ((MAX_ASSET_BYTES + 2) // 3) * 4:
        raise FileTooLarge()
    try:
        content = base64.b64decode(value, validate=True)
        return ParsedAsset(content, raw["sha256"], raw["width"], raw["height"], raw["mime_type"], raw["kind"], raw["caption"], raw["page"])
    except (binascii.Error, ValueError, TypeError):
        raise InvalidAsset() from None


def asset_object_key(tenant_id: str, doc_id: str, kind: str, sha256: str) -> str:
    if not isinstance(tenant_id, str) or not isinstance(doc_id, str) or _HEX32.fullmatch(tenant_id) is None or _HEX32.fullmatch(doc_id) is None:
        raise InvalidAsset()
    if kind not in {"image", "table"} or not isinstance(sha256, str) or _SHA.fullmatch(sha256) is None:
        raise InvalidAsset()
    return f"{tenant_id}/{doc_id}/{'tables' if kind == 'table' else 'images'}/{sha256}.png"
