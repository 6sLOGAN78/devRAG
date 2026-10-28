"""XLSX parser (PARSE-10): read-only, cached values, header row repeated per group, cell cap."""

from __future__ import annotations

import zipfile
from collections.abc import Iterator

import openpyxl
from lxml import etree

from rag.parsers.errors import FileDamaged, FileTooLarge, NoReadableText
from rag.parsers.limits import check_ooxml_limits
from rag.parsers.tabletext import render_table
from rag.parsers.types import ParsedBlock, ParseLimits, ParseReport, SourceFile

GROUP_ROWS = 20
_DAMAGE = (zipfile.BadZipFile, KeyError, ValueError, AttributeError, etree.XMLSyntaxError, OSError)


def _extract(source: SourceFile, report: ParseReport, max_cells: int) -> list[ParsedBlock]:
    wb = openpyxl.load_workbook(str(source.path), read_only=True, data_only=True)
    blocks: list[ParsedBlock] = []
    cells = 0
    stopped = False
    try:
        for ws in wb.worksheets:
            header: list[object] | None = None
            group: list[list[object]] = []

            def flush() -> None:
                if group:
                    rows = [header, *group] if header is not None else list(group)
                    blocks.append(ParsedBlock(f"{ws.title}\n{render_table(rows)}", "sheet"))
                    group.clear()

            for row in ws.iter_rows(values_only=True):
                if not any(c is not None and str(c).strip() for c in row):
                    continue
                cells += len(row)
                if cells > max_cells:
                    stopped = True
                    break
                if header is None:
                    header = list(row)
                    continue
                group.append(list(row))
                if len(group) >= GROUP_ROWS:
                    flush()
            flush()
            if header is not None and not blocks_for(blocks, ws.title):
                blocks.append(ParsedBlock(f"{ws.title}\n{render_table([header])}", "sheet"))
            if stopped:
                break
    finally:
        wb.close()
    if stopped:
        report.add_note(f"reading stopped after {max_cells} cells")
    return blocks


def blocks_for(blocks: list[ParsedBlock], title: str) -> bool:
    return any(b.text.startswith(f"{title}\n") for b in blocks)


def _extract_records(source: SourceFile, max_cells: int) -> list[ParsedBlock]:
    from rag.parsers.records import MAX_RECORDS, row_record, pointer_part

    from datetime import date, datetime, time

    wb = openpyxl.load_workbook(str(source.path), read_only=True, data_only=True)
    blocks = []
    cells = 0
    try:
        for ws in wb.worksheets:
            header = None
            for number, row in enumerate(ws.iter_rows(values_only=True), 1):
                values = list(row)
                while values and values[-1] in (None, ""):
                    values.pop()
                if not values:
                    continue
                cells += len(row)
                if cells > max_cells or len(blocks) >= MAX_RECORDS:
                    raise FileTooLarge()
                prefix = "/" + pointer_part(ws.title) + "/" + str(number)
                if header is None:
                    header = values
                    row_record(header, [""] * len(header), prefix)
                    continue
                if len(values) > len(header):
                    raise FileDamaged()
                values += [None] * (len(header) - len(values))
                values = [value.isoformat() if isinstance(value, (datetime, date, time)) else value for value in values]
                record = row_record(header, values, prefix, (number, number))
                blocks.append(ParsedBlock(record.text(), "sheet", record=record, line_range=record.line_range))
    finally:
        wb.close()
    return blocks


def parse(
    source: SourceFile,
    report: ParseReport,
    *,
    page_range: tuple[int, int] | None = None,
    limits: ParseLimits | None = None,
    structured_records: bool = False,
) -> Iterator[ParsedBlock]:
    del page_range
    limits = limits or ParseLimits()
    check_ooxml_limits(source.path)
    try:
        blocks = _extract_records(source, limits.xlsx_max_cells) if structured_records else _extract(source, report, limits.xlsx_max_cells)
    except _DAMAGE:
        raise FileDamaged() from None
    if not blocks:
        raise NoReadableText()
    return iter(blocks)
