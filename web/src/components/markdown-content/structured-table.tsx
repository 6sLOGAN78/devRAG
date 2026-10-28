import type { TableView } from "@/services/table-features";

/** The same semantic table styling as Markdown, with explicit source spans and text-only cells. */
export function StructuredTable({ table }: { table: TableView }) {
  const rows = Array.from({ length: table.rows }, (_, row) => table.cells.filter((cell) => cell.row === row));
  return <div className="my-2 overflow-x-auto"><table data-testid="source-structured-table" className="w-full border-collapse text-base">
    {table.caption ? <caption className="mb-2 text-left text-sm font-semibold">{table.caption}</caption> : null}
    <tbody>{rows.map((cells, row) => <tr key={row}>{cells.map((cell) => {
      const Cell = cell.header ? "th" : "td";
      return <Cell key={cell.column} rowSpan={cell.rowspan} colSpan={cell.colspan} className={cell.header ? "border-b px-3 py-2 text-left text-xs font-semibold" : "border-b px-3 py-2 align-top"}>{cell.text}</Cell>;
    })}</tr>)}</tbody>
  </table></div>;
}
