"""Bounded structured table values shared across native transport, indexing and UI DTOs."""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass

MAX_CELLS = 4096
MAX_TABLE_TEXT = 65536


@dataclass(frozen=True)
class TableCell:
    row: int
    column: int
    text: str
    rowspan: int = 1
    colspan: int = 1
    header: bool = False

    def __post_init__(self):
        if any(type(v) is not int for v in (self.row, self.column, self.rowspan, self.colspan)) or min(self.row, self.column) < 0 or min(self.rowspan, self.colspan) < 1:
            raise ValueError("invalid table cell")
        if not isinstance(self.text, str) or len(self.text) > 4096 or type(self.header) is not bool:
            raise ValueError("invalid table cell")


@dataclass(frozen=True)
class Table:
    rows: int
    columns: int
    cells: tuple[TableCell, ...]
    caption: str = ""
    asset_id: str = ""
    asset_sha256: str = ""

    def __post_init__(self):
        if type(self.rows) is not int or type(self.columns) is not int or not 1 <= self.rows <= 256 or not 1 <= self.columns <= 128 or self.rows * self.columns > MAX_CELLS:
            raise ValueError("invalid table dimensions")
        if not isinstance(self.cells, tuple) or len(self.cells) > MAX_CELLS or any(not isinstance(c, TableCell) for c in self.cells) or sum(len(c.text) for c in self.cells) > MAX_TABLE_TEXT:
            raise ValueError("invalid table cells")
        if not isinstance(self.caption, str) or len(self.caption) > 1024:
            raise ValueError("invalid table caption")
        if not isinstance(self.asset_id, str) or (self.asset_id and re.fullmatch(r"[0-9a-f]{32}", self.asset_id) is None):
            raise ValueError("invalid table asset")
        if not isinstance(self.asset_sha256, str) or (self.asset_sha256 and re.fullmatch(r"[0-9a-f]{64}", self.asset_sha256) is None):
            raise ValueError("invalid table asset")
        occupied = set()
        for cell in self.cells:
            if not isinstance(cell, TableCell) or cell.row + cell.rowspan > self.rows or cell.column + cell.colspan > self.columns:
                raise ValueError("invalid table span")
            for row in range(cell.row, cell.row + cell.rowspan):
                for column in range(cell.column, cell.column + cell.colspan):
                    if (row, column) in occupied:
                        raise ValueError("overlapping table span")
                    occupied.add((row, column))
        if len(occupied) != self.rows * self.columns:
            raise ValueError("incomplete table cells")

    def html(self) -> str:
        out = ["<table>"]
        if self.caption:
            out.append("<caption>" + html.escape(self.caption) + "</caption>")
        by_row = {row: [] for row in range(self.rows)}
        for cell in sorted(self.cells, key=lambda c: (c.row, c.column)):
            tag = "th" if cell.header else "td"
            attrs = (' rowspan="' + str(cell.rowspan) + '"' if cell.rowspan > 1 else "") + (' colspan="' + str(cell.colspan) + '"' if cell.colspan > 1 else "")
            by_row[cell.row].append(f"<{tag}{attrs}>{html.escape(cell.text)}</{tag}>")
        out.extend("<tr>" + "".join(by_row[row]) + "</tr>" for row in range(self.rows))
        out.append("</table>")
        return "\n".join(out)

    def plain_text(self) -> str:
        return "\n".join(filter(None, [self.caption, *[" | ".join(c.text for c in sorted(self.cells, key=lambda c: c.column) if c.row == row).rstrip() for row in range(self.rows)]]))

    def to_wire(self) -> dict:
        return {**asdict(self), "cells": [asdict(cell) for cell in self.cells], "html": self.html()}

    def to_dto(self) -> dict:
        return {key: value for key, value in self.to_wire().items() if key not in {"asset_sha256", "html"}}

    @classmethod
    def from_wire(cls, raw: object):
        if not isinstance(raw, dict) or set(raw) != {"rows", "columns", "cells", "caption", "asset_id", "asset_sha256", "html"} or not isinstance(raw["cells"], list) or len(raw["cells"]) > MAX_CELLS:
            raise ValueError("invalid table response")
        if any(not isinstance(c, dict) or set(c) != {"row", "column", "text", "rowspan", "colspan", "header"} for c in raw["cells"]):
            raise ValueError("invalid table response")
        made = cls(raw["rows"], raw["columns"], tuple(TableCell(**c) for c in raw["cells"]), raw["caption"], raw["asset_id"], raw["asset_sha256"])
        if raw["html"] != made.html():
            raise ValueError("invalid table HTML")
        return made

    @classmethod
    def from_dto(cls, raw: object):
        if not isinstance(raw, dict) or set(raw) != {"rows", "columns", "cells", "caption", "asset_id"} or not isinstance(raw["cells"], list) or len(raw["cells"]) > MAX_CELLS:
            raise ValueError("invalid table view")
        if any(not isinstance(c, dict) or set(c) != {"row", "column", "text", "rowspan", "colspan", "header"} for c in raw["cells"]):
            raise ValueError("invalid table view")
        made = cls(raw["rows"], raw["columns"], tuple(TableCell(**c) for c in raw["cells"]), raw["caption"], raw["asset_id"])
        return made
