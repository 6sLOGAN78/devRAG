import { AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createChunk, listChunks, updateChunk } from "./chunk-service";
import { http } from "./http";

const originalAdapter = http.defaults.adapter;
let body: unknown;
let seen: InternalAxiosRequestConfig[] = [];
const adapter: AxiosAdapter = (config) => {
  seen.push(config);
  return Promise.resolve({ data: body, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;
};
beforeEach(() => {
  seen = [];
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
});
const success = (data: unknown) => ({ code: 0, message: "", data });

const D = "0123456789abcdef0123456789abcdef";
const position = { page: 1, x0: 1, x1: 2, top: 3, bottom: 4 };
const chunk = { id: "c1", text: "hello", positions: [position], origin: "edited", enabled: false };

describe("listChunks (UI-16)", () => {
  it("sends bounded paging and filters and maps the page by an explicit field list", async () => {
    body = success({ items: [{ ...chunk, secret: "x" }], total: 9, page_sizes: { "1": [600, 800], "2": ["a", 1] } });
    const page = await listChunks({ datasetId: D, docId: "d1", page: 0, size: 500, keywords: "k".repeat(300), available: false });
    expect(seen[0]?.url).toBe(`/api/v1/datasets/${D}/documents/d1/chunks`);
    expect(seen[0]?.method).toBe("get");
    expect(seen[0]?.silent).toBe(true);
    const params = seen[0]?.params as Record<string, unknown>;
    expect(params).toMatchObject({ page: 1, size: 100, available: 0 });
    expect((params.keywords as string).length).toBe(128);
    expect(page).toEqual({ items: [chunk], total: 9, pageSizes: { "1": [600, 800] } });
  });

  it("omits empty keywords and an unset availability", async () => {
    body = success({ items: [], total: 0, page_sizes: {} });
    await listChunks({ datasetId: D, docId: "d1", page: 2, size: 20, keywords: "" });
    expect(seen[0]?.params).toEqual({ page: 2, size: 20 });
  });

  it("drops a position with a non-finite number and falls back to the parsed origin", async () => {
    body = success({
      items: [{ ...chunk, origin: "<b>", enabled: true, positions: [position, { ...position, x0: "1" }, { ...position, top: null }, "x"] }],
      total: 1,
      page_sizes: {},
    });
    const { items } = await listChunks({ datasetId: D, docId: "d1", page: 1, size: 20, keywords: "" });
    expect(items[0]?.positions).toEqual([position]);
    expect(items[0]?.origin).toBe("parsed");
  });
});

describe("createChunk and updateChunk (UI-17)", () => {
  it("creates with content_with_weight and a 45 s timeout", async () => {
    body = success(chunk);
    expect(await createChunk(D, "d1", "hello")).toEqual(chunk);
    expect(seen[0]?.method).toBe("post");
    expect(JSON.parse(seen[0]?.data as string)).toEqual({ content_with_weight: "hello" });
    expect(seen[0]?.timeout).toBe(45000);
    expect(seen[0]?.silent).toBe(true);
  });

  it("uses 45 s for a text change and the default for a switch alone", async () => {
    body = success(chunk);
    await updateChunk(D, "d1", "c/1", { text: "new" });
    expect(seen[0]?.url).toBe(`/api/v1/datasets/${D}/documents/d1/chunks/c%2F1`);
    expect(seen[0]?.method).toBe("patch");
    expect(JSON.parse(seen[0]?.data as string)).toEqual({ content_with_weight: "new" });
    expect(seen[0]?.timeout).toBe(45000);
    seen = [];
    await updateChunk(D, "d1", "c1", { enabled: false });
    expect(JSON.parse(seen[0]?.data as string)).toEqual({ available: false });
    expect(seen[0]?.timeout).toBe(http.defaults.timeout);
    expect(seen[0]?.silent).toBe(true);
  });
});
