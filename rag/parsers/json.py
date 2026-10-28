"""Strict JSON records with bounded structure and deterministic JSON-pointer paths."""

from __future__ import annotations

import json
import math

from rag.parsers.errors import FileDamaged, FileTooLarge, NoReadableText
from rag.parsers.records import MAX_FIELDS, MAX_RECORDS, Record, RecordField, pointer_part
from rag.parsers.txt import _decode, _read
from rag.parsers.types import ParsedBlock, ParseLimits

MAX_DEPTH = 32
MAX_VALUES = 100000


def _scan(text: str) -> None:
    depth = values = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            values += 1
            if depth > MAX_DEPTH:
                raise FileTooLarge()
        elif char in "]}":
            depth -= 1
        elif char in ",:":
            values += 1
        if values > MAX_VALUES:
            raise FileTooLarge()


def _object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise FileDamaged()
        result[name] = value
    return result


def _finite(raw):
    value = float(raw)
    if not math.isfinite(value):
        raise FileDamaged()
    return value


def _constant(_):
    raise FileDamaged()


def parse(source, report, *, page_range=None, limits=None):
    del page_range
    limits = limits or ParseLimits()
    text = _decode(_read(source, limits.max_text_bytes))
    if not text.strip():
        raise NoReadableText()
    _scan(text)
    try:
        value = json.loads(text, object_pairs_hook=_object, parse_float=_finite, parse_constant=_constant)
    except (ValueError, RecursionError, UnicodeError):
        raise FileDamaged() from None
    items = list(enumerate(value)) if isinstance(value, list) else [(None, value)]
    if len(items) > MAX_RECORDS:
        raise FileTooLarge()
    blocks = []
    for index, item in items:
        fields = []

        def visit(node, path, name):
            if isinstance(node, dict):
                for key in sorted(node):
                    visit(node[key], path + "/" + pointer_part(key), key)
            elif isinstance(node, list):
                for offset, part in enumerate(node):
                    visit(part, path + "/" + str(offset), str(offset))
            else:
                fields.append(RecordField(name, path, node))
                if len(fields) > MAX_FIELDS:
                    raise FileTooLarge()

        visit(item, "" if index is None else "/" + str(index), "$")
        if fields:
            record = Record(tuple(fields))
            blocks.append(ParsedBlock(record.text(), record=record))
    if not blocks:
        raise NoReadableText()
    report.pages_total = None
    return iter(blocks)
