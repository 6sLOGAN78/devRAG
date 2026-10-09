import { AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deleteDocuments, listDocuments, uploadDocument } from "./document-service";
import { ApiError, http } from "./http";

const originalAdapter = http.defaults.adapter;
let body: unknown;
let seen: InternalAxiosRequestConfig[] = [];
let progress: Array<{ loaded: number; total?: number }> = [];

const adapter: AxiosAdapter = (config) => {
  seen.push(config);
  for (const event of progress) config.onUploadProgress?.(event as never);
  return Promise.resolve({ data: body, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;
};

beforeEach(() => {
  seen = [];
  progress = [];
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  vi.restoreAllMocks();
});

const success = (data: unknown) => ({ code: 0, message: "", data });

const DATASET = "0123456789abcdef0123456789abcdef";

const documentDto = {
  id: "d1",
  name: "report(1).pdf",
  size: 2048,
  type: "pdf",
  suffix: "pdf",
  run: "0",
  progress: 0,
  dataset_id: DATASET,
  created_by: "u1",
  parser_id: "naive",
  chunk_num: 0,
  token_num: 0,
  create_time: 1700000000000,
  update_time: 1700000100000,
};

const expectedView = {
  id: "d1",
  name: "report(1).pdf",
  size: 2048,
  type: "pdf",
  suffix: "pdf",
  run: "0",
  progress: 0,
  datasetId: DATASET,
  createdBy: "u1",
  parserId: "naive",
  chunkNum: 0,
  updateTime: 1700000100000,
  createTime: 1700000000000,
};

describe("uploadDocument (DOC-01, Pitfall 8)", () => {
  const pdf = new File([new Uint8Array(8)], "report.pdf", { type: "application/pdf" });

  it("posts one multipart file with dataset_id in the query and no client timeout", async () => {
    body = success([documentDto]);
    const controller = new AbortController();
    await uploadDocument(DATASET, pdf, { signal: controller.signal });
    expect(seen).toHaveLength(1);
    const config = seen[0]!;
    expect(config.url).toBe("/api/v1/documents/upload");
    expect(config.method).toBe("post");
    expect(config.params).toEqual({ dataset_id: DATASET });
    expect(config.data).toBeInstanceOf(FormData);
    const sent = (config.data as FormData).getAll("file");
    expect(sent).toHaveLength(1);
    expect((sent[0] as File).name).toBe("report.pdf");
    expect(config.timeout).toBe(0);
    expect(config.silent).toBe(true);
    expect(config.signal).toBe(controller.signal);
  });

  it("sets no Content-Type of its own, so the browser writes the multipart boundary", async () => {
    body = success([documentDto]);
    const spy = vi.spyOn(http, "request");
    await uploadDocument(DATASET, pdf);
    const requested = spy.mock.calls[0]![0];
    expect(requested.headers).toBeUndefined();
  });

  it("returns the first document the server stored, mapped by an explicit field list", async () => {
    body = success([{ ...documentDto, location: "tenant/secret-key", thumbnail: "x" }]);
    const view = await uploadDocument(DATASET, pdf);
    expect(view).toEqual(expectedView);
    expect(JSON.stringify(view)).not.toContain("secret-key");
  });

  it("passes the browser's upload progress to the caller as loaded and total", async () => {
    body = success([documentDto]);
    progress = [{ loaded: 50, total: 100 }, { loaded: 100, total: 100 }];
    const reports: Array<[number, number | undefined]> = [];
    await uploadDocument(DATASET, pdf, { onProgress: (loaded, total) => reports.push([loaded, total]) });
    expect(reports).toEqual([[50, 100], [100, 100]]);
  });

  it("fails with a clear error when the server answers success with no document", async () => {
    body = success([]);
    await expect(uploadDocument(DATASET, pdf)).rejects.toBeInstanceOf(ApiError);
    body = success(null);
    await expect(uploadDocument(DATASET, pdf)).rejects.toBeInstanceOf(ApiError);
  });
});

describe("listDocuments (DOC-08)", () => {
  it("sends page, page_size and keywords and maps items by an explicit field list", async () => {
    body = success({ items: [{ ...documentDto, location: "k", status: "1" }], total: 41 });
    const result = await listDocuments({ datasetId: DATASET, page: 2, pageSize: 20, keywords: "rep" });
    expect(seen[0]?.url).toBe(`/api/v1/datasets/${DATASET}/documents`);
    expect(seen[0]?.method).toBe("get");
    expect(seen[0]?.params).toEqual({ page: 2, page_size: 20, keywords: "rep" });
    expect(seen[0]?.silent).toBe(true);
    expect(result).toEqual({ items: [expectedView], total: 41 });
  });

  it("omits an empty keywords parameter and clamps page, page_size and keywords before the request", async () => {
    body = success({ items: [], total: 0 });
    await listDocuments({ datasetId: DATASET, page: 0, pageSize: 500, keywords: "" });
    expect(seen[0]?.params).toEqual({ page: 1, page_size: 100 });
    seen = [];
    await listDocuments({ datasetId: DATASET, page: 1.9, pageSize: 20, keywords: "k".repeat(300) });
    expect((seen[0]?.params as Record<string, unknown>).page).toBe(1);
    expect(((seen[0]?.params as Record<string, unknown>).keywords as string).length).toBe(128);
  });

  it("percent-encodes the dataset id in the path", async () => {
    body = success({ items: [], total: 0 });
    await listDocuments({ datasetId: "a/b", page: 1, pageSize: 20, keywords: "" });
    expect(seen[0]?.url).toBe("/api/v1/datasets/a%2Fb/documents");
  });

  it("treats a missing items list as empty", async () => {
    body = success({ total: "7" });
    expect(await listDocuments({ datasetId: DATASET, page: 1, pageSize: 20, keywords: "" })).toEqual({ items: [], total: 7 });
  });
});

describe("deleteDocuments (DOC-14)", () => {
  it("sends the ids as a JSON body with DELETE and returns how many were removed", async () => {
    body = success({ deleted: 2 });
    const deleted = await deleteDocuments(DATASET, ["d1", "d2"]);
    expect(seen[0]?.method).toBe("delete");
    expect(seen[0]?.url).toBe(`/api/v1/datasets/${DATASET}/documents`);
    expect(JSON.parse(seen[0]?.data as string)).toEqual({ ids: ["d1", "d2"] });
    expect(seen[0]?.silent).toBe(true);
    expect(deleted).toBe(2);
  });
});
