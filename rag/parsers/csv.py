"""Quoted CSV records, preserving exact scalar values and physical line evidence."""

from __future__ import annotations

import csv
import io

from rag.parsers.errors import FileDamaged, FileTooLarge, NoReadableText
from rag.parsers.records import MAX_RECORDS, row_record
from rag.parsers.txt import _decode, _read
from rag.parsers.types import ParsedBlock, ParseLimits


def parse(source, report, *, page_range=None, limits=None):
    del page_range
    limits = limits or ParseLimits()
    text = _decode(_read(source, limits.max_text_bytes))
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    blocks = []
    try:
        headers = next(reader)
        row_record(headers, [""] * len(headers), "/header")
        previous = reader.line_num
        for values in reader:
            start, previous = previous + 1, reader.line_num
            if not values:
                continue
            if len(blocks) >= MAX_RECORDS or previous > 1_000_000:
                raise FileTooLarge()
            record = row_record(headers, values, "/" + str(len(blocks)), (start, previous))
            blocks.append(ParsedBlock(record.text(), record=record, line_range=record.line_range))
    except StopIteration:
        raise NoReadableText() from None
    except (csv.Error, UnicodeError):
        raise FileDamaged() from None
    if not blocks:
        raise NoReadableText()
    report.pages_total = None
    return iter(blocks)
