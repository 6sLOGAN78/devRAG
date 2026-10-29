"""One logical data row with table title and complete column-header context."""

from dataclasses import dataclass
from rag.chunking.types import Chunk
from rag.chunking.errors import ChunkTooLong
from rag.nlp.token_count import count_tokens
from rag.parsers.errors import FileDamaged
from rag.parsers.tables import Table, TableCell


@dataclass(frozen=True)
class TableConfig:
    chunk_token_num: int = 512


def expanded(table):
    grid = [[None] * table.columns for _ in range(table.rows)]
    for cell in table.cells:
        for r in range(cell.row, cell.row + cell.rowspan):
            for c in range(cell.column, cell.column + cell.colspan):
                grid[r][c] = cell
    return grid


def chunk(blocks, cfg):
    index = 0
    saw_table = False
    saw_text = False
    for block in blocks:
        table = block.table
        if table is None:
            saw_text = saw_text or bool(block.text.strip())
            continue
        saw_table = True
        grid = expanded(table)
        header_rows = max((c.row + c.rowspan for c in table.cells if c.header), default=1)
        if header_rows >= table.rows:
            continue
        labels = [" / ".join(dict.fromkeys(grid[r][c].text.strip() for r in range(header_rows) if grid[r][c].text.strip())) or f"Column {c + 1}" for c in range(table.columns)]
        for row in range(header_rows, table.rows):
            values = [cell.text for cell in grid[row]]
            if not any(v.strip() for v in values):
                continue
            text = "\n".join(filter(None, [table.caption, *[f"{label}: {value}" for label, value in zip(labels, values, strict=True)]]))
            tokens = count_tokens(text)
            if tokens > min(max(1, cfg.chunk_token_num), 8191):
                raise ChunkTooLong()
            cells = tuple([TableCell(0, c, label, header=True) for c, label in enumerate(labels)] + [TableCell(1, c, value) for c, value in enumerate(values)])
            view = Table(2, table.columns, cells, table.caption, table.asset_id, table.asset_sha256)
            lines = ()
            if block.line_range:
                start, end = block.line_range
                lines = (block.line_range,) if start == end or table.rows - header_rows == 1 else ((start + row - header_rows, start + row - header_rows),)
            yield Chunk(text, block.boxes, block.page_sizes, tokens, index, tables=(view,), image_ids=block.image_ids, source_lines=lines)
            index += 1

    if saw_text and not saw_table:
        raise FileDamaged()
