import { asRecord } from "./mapping";

export interface TableCellView { row: number; column: number; text: string; rowspan: number; colspan: number; header: boolean }
export interface TableView { rows: number; columns: number; cells: TableCellView[]; caption: string; assetId: string }

/** Table text is copied as text, spans are bounded integers, and only an opaque crop id crosses the boundary. */
export function tableViewsOf(raw: unknown): TableView[] {
  if (!Array.isArray(raw) || raw.length > 16) return [];
  return raw.flatMap((value): TableView[] => {
    const t = asRecord(value);
    if (!Number.isInteger(t.rows) || !Number.isInteger(t.columns)) return [];
    const rows = t.rows as number, columns = t.columns as number;
    if (rows < 1 || rows > 256 || columns < 1 || columns > 128 || rows * columns > 4096 || !Array.isArray(t.cells) || t.cells.length > 4096 || typeof t.asset_id !== "string" || !/^[a-f0-9]{32}$/.test(t.asset_id) || typeof t.caption !== "string" || t.caption.length > 1024) return [];
    const seen = new Set<string>(), cells: TableCellView[] = [];
    let size = 0;
    for (const value of t.cells) {
      const c = asRecord(value);
      if (![c.row, c.column, c.rowspan, c.colspan].every((n) => typeof n === "number" && Number.isInteger(n)) || typeof c.text !== "string" || c.text.length > 4096 || typeof c.header !== "boolean") return [];
      const row = c.row as number, column = c.column as number, rowspan = c.rowspan as number, colspan = c.colspan as number;
      if (row < 0 || column < 0 || rowspan < 1 || colspan < 1 || row + rowspan > rows || column + colspan > columns) return [];
      size += c.text.length; if (size > 65536) return [];
      for (let r = row; r < row + rowspan; r++) for (let col = column; col < column + colspan; col++) {
        const key = `${r}:${col}`; if (seen.has(key)) return []; seen.add(key);
      }
      cells.push({ row, column, rowspan, colspan, text: c.text, header: c.header });
    }
    if (seen.size !== rows * columns) return [];
    return [{ rows, columns, cells: cells.sort((a, b) => a.row - b.row || a.column - b.column), caption: t.caption, assetId: t.asset_id }];
  });
}
