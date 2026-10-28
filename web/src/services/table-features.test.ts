import { describe, expect, it } from "vitest";
import { tableViewsOf } from "./table-features";

const table = () => ({ rows: 1, columns: 1, caption: "literal <b>title</b>", asset_id: "a".repeat(32), cells: [{ row: 0, column: 0, text: "<img src=x onerror=alert(1)>", rowspan: 1, colspan: 1, header: false }] });
describe("bounded source table views", () => {
  it("retains literal cell text and an opaque crop id without copying internal fields", () => {
    const result = tableViewsOf([{ ...table(), object_key: "/private/file", html: "<script>bad</script>" }]);
    expect(result[0]?.cells[0]?.text).toBe("<img src=x onerror=alert(1)>");
    expect(result[0]?.caption).toBe("literal <b>title</b>");
    expect(result[0]).not.toHaveProperty("object_key"); expect(result[0]).not.toHaveProperty("html");
  });
  it.each([NaN, Infinity, 0, -1, 4097])("rejects invalid spans %s", (span) => {
    const raw = table(); raw.cells[0]!.rowspan = span; expect(tableViewsOf([raw])).toEqual([]);
  });
  it("rejects overlapping cells and missing slots", () => {
    const raw = table(); raw.cells.push({ ...raw.cells[0]! }); expect(tableViewsOf([raw])).toEqual([]);
    const missing = table(); missing.cells = []; expect(tableViewsOf([missing])).toEqual([]);
  });
  it("rejects path-like ids", () => expect(tableViewsOf([{ ...table(), asset_id: "../other.png" }])).toEqual([]));
});
