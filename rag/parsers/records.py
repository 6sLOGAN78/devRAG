"""Bounded immutable scalar records shared by structured parsers and Q&A."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from rag.parsers.errors import FileDamaged, FileTooLarge

MAX_RECORDS = 10000
MAX_FIELDS = 1024
MAX_VALUE_CHARS = 65536
MAX_RECORD_BYTES = 1024 * 1024
Scalar = str | int | float | bool | None


def pointer_part(value: str | int) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def scalar_text(value: Scalar) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)


@dataclass(frozen=True)
class RecordField:
    name: str
    path: str
    value: Scalar

    def __post_init__(self):
        if not isinstance(self.name, str) or not isinstance(self.path, str) or type(self.value) not in {str, int, float, bool, type(None)}:
            raise FileDamaged()
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise FileDamaged()
        if len(self.name) > 256 or len(self.path) > 4096 or len(scalar_text(self.value)) > MAX_VALUE_CHARS:
            raise FileTooLarge()
        try:
            scalar_text(self.value).encode("utf-8")
            self.path.encode("utf-8")
        except UnicodeError:
            raise FileDamaged() from None


@dataclass(frozen=True)
class Record:
    fields: tuple[RecordField, ...]
    line_range: tuple[int, int] | None = None

    def __post_init__(self):
        if not isinstance(self.fields, tuple) or not all(isinstance(field, RecordField) for field in self.fields):
            raise FileDamaged()
        if len(self.fields) > MAX_FIELDS or sum(len(scalar_text(f.value).encode()) + len(f.path.encode()) for f in self.fields) > MAX_RECORD_BYTES:
            raise FileTooLarge()
        if len({f.path for f in self.fields}) != len(self.fields):
            raise FileDamaged()

    def text(self) -> str:
        return "\n".join(f"{json.dumps(f.path, ensure_ascii=False)}: {scalar_text(f.value)}" for f in self.fields)


def row_record(headers, values, prefix: str, line_range=None) -> Record:
    if not headers or len(headers) > 256:
        raise FileTooLarge()
    if len(headers) != len(values) or any(not isinstance(h, str) or not h.strip() for h in headers):
        raise FileDamaged()
    normalized = [h.strip().casefold() for h in headers]
    if len(set(normalized)) != len(normalized):
        raise FileDamaged()
    return Record(tuple(RecordField(h, prefix + "/" + pointer_part(h), value) for h, value in zip(headers, values, strict=True)), line_range)
