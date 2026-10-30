import { AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { confirmCountsOf, deleteDocuments, getDocument, listDocuments, parseDocuments, setDocumentsEnabled, updateDocumentSettings, uploadDocument } from "./document-service";
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
  metadata: {},
  chunkNum: 0,
  updateTime: 1700000100000,
  createTime: 1700000000000,
  chunkCount: 0,
  tokenNum: 0,
  parseable: true,
  enabled: true,
  thumbnail: null,
  lastLogId: null,
  pagesTotal: null,
  pagesWithoutText: null,
  progressMessage: "",
  error: null,
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

describe("toDocument on the Phase 4 rows (UI-13)", () => {
  const row = { ...documentDto, chunk_count: 7, token_num: 90, parseable: false, enabled: false, last_log_id: "log1", pages_total: 12, pages_without_text: 2, progress_message: "Parsing", error: { step: "parse", code: "x", message: "bad", extra: 1 } };

  it("maps the new fields and prefers chunk_count over chunk_num", async () => {
    body = success({ items: [{ ...row, chunk_num: 3, location: "tenant/secret-key" }], total: 1 });
    const { items } = await listDocuments({ datasetId: DATASET, page: 1, pageSize: 20, keywords: "" });
    expect(items[0]).toMatchObject({ chunkCount: 7, chunkNum: 7, tokenNum: 90, parseable: false, enabled: false, lastLogId: "log1", pagesTotal: 12, pagesWithoutText: 2, progressMessage: "Parsing" });
    expect(items[0]!.error).toEqual({ step: "parse", code: "x", message: "bad" });
    expect(JSON.stringify(items[0])).not.toContain("secret-key");
  });

  it("keeps only a base64 JPEG or PNG thumbnail", async () => {
    const make = (thumbnail: unknown) => ({ ...documentDto, thumbnail });
    body = success({
      items: [make("data:image/jpeg;base64,AAAA"), make("data:image/png;base64,AAAA"), make("data:image/svg+xml;base64,AAAA"), make("javascript:alert(1)"), make("https://x/y.png"), make(5)],
      total: 6,
    });
    const { items } = await listDocuments({ datasetId: DATASET, page: 1, pageSize: 20, keywords: "" });
    expect(items.map((item) => item.thumbnail)).toEqual(["data:image/jpeg;base64,AAAA", "data:image/png;base64,AAAA", null, null, null, null]);
  });

  it("cuts a progress message at 300 characters", async () => {
    body = success({ items: [{ ...documentDto, progress_message: "m".repeat(900) }], total: 1 });
    const { items } = await listDocuments({ datasetId: DATASET, page: 1, pageSize: 20, keywords: "" });
    expect(items[0]!.progressMessage).toHaveLength(300);
  });
});

describe("parseDocuments (UI-13)", () => {
  it("posts doc_ids and run with a 30 s timeout, silently, and omits confirm_replace unless asked", async () => {
    body = success({ started: [{ id: "d1", tasks: 2 }], cancelled: null });
    const result = await parseDocuments(DATASET, ["d1"], "1");
    expect(seen[0]?.url).toBe(`/api/v1/datasets/${DATASET}/documents/parse`);
    expect(seen[0]?.method).toBe("post");
    expect(JSON.parse(seen[0]?.data as string)).toEqual({ doc_ids: ["d1"], run: "1" });
    expect(seen[0]?.timeout).toBe(30000);
    expect(seen[0]?.silent).toBe(true);
    expect(result).toEqual({ started: ["d1"], cancelled: [] });
    seen = [];
    body = success({ started: null, cancelled: ["d1"] });
    expect(await parseDocuments(DATASET, ["d1"], "2", true)).toEqual({ started: [], cancelled: ["d1"] });
    expect(JSON.parse(seen[0]?.data as string)).toEqual({ doc_ids: ["d1"], run: "2", confirm_replace: true });
  });

  it("rejects a 409 confirm_required with the ApiError and reads the counts from it", async () => {
    http.defaults.adapter = (config) =>
      Promise.reject(
        Object.assign(new Error("conflict"), {
          isAxiosError: true,
          config,
          response: {
            status: 409,
            data: { code: 409, message: "confirm", data: { documents: [{ id: "d1", name: "a.pdf", chunk_count: 4, edited_count: 1, manual_count: 2, secret: "x" }] } },
            headers: new AxiosHeaders(),
            config,
          },
        }),
      );
    const failure = await parseDocuments(DATASET, ["d1"], "1").catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(confirmCountsOf(failure)).toEqual([{ id: "d1", name: "a.pdf", chunkCount: 4, editedCount: 1, manualCount: 2 }]);
    expect(confirmCountsOf(new Error("x"))).toEqual([]);
  });
});

describe("setDocumentsEnabled, getDocument, updateDocumentSettings (UI-14, UI-15)", () => {
  it("sends doc_ids with status 1 or 0 and returns the updated ids", async () => {
    body = success({ updated: ["d1", "d2"], enabled: false });
    const result = await setDocumentsEnabled(DATASET, ["d1", "d2"], false);
    expect(seen[0]?.url).toBe(`/api/v1/datasets/${DATASET}/documents/batch-update-status`);
    expect(JSON.parse(seen[0]?.data as string)).toEqual({ doc_ids: ["d1", "d2"], status: "0" });
    expect(seen[0]?.timeout).toBe(30000);
    expect(seen[0]?.silent).toBe(true);
    expect(result).toEqual({ updated: ["d1", "d2"], enabled: false });
  });

  it("maps the detail view and limits preview to pages or none", async () => {
    const detail = { ...documentDto, chunk_token_num: 256, delimiter: "\n", overlapped_percent: 10, pages_total: 3 };
    body = success({ ...detail, preview: "pages" });
    const view = await getDocument(DATASET, "d1");
    expect(seen[0]?.url).toBe(`/api/v1/datasets/${DATASET}/documents/d1`);
    expect(seen[0]?.silent).toBe(true);
    expect(view).toMatchObject({ chunkTokenNum: 256, delimiter: "\n", overlappedPercent: 10, preview: "pages", pagesTotal: 3 });
    body = success({ ...detail, preview: "<script>" });
    expect((await getDocument(DATASET, "d1")).preview).toBe("none");
  });

  it("fails clearly when the detail has no id", async () => {
    body = success({});
    await expect(getDocument(DATASET, "d1")).rejects.toBeInstanceOf(ApiError);
  });

  it("sends only the keys given", async () => {
    body = success({ ...documentDto, chunk_token_num: 128 });
    await updateDocumentSettings(DATASET, "d1", { chunkTokenNum: 128 });
    expect(seen[0]?.method).toBe("patch");
    expect(JSON.parse(seen[0]?.data as string)).toEqual({ parser_config: { chunk_token_num: 128 } });
    seen = [];
    await updateDocumentSettings(DATASET, "d1", { parserId: "book" });
    expect(JSON.parse(seen[0]?.data as string)).toEqual({ parser_id: "book" });
    expect(seen[0]?.silent).toBe(true);
  });

  it("encodes ids in every new path and puts no token in a URL", async () => {
    body = success({ ...documentDto });
    await getDocument(DATASET, "a/b");
    expect(seen[0]?.url).toBe(`/api/v1/datasets/${DATASET}/documents/a%2Fb`);
    expect(seen[0]?.url).not.toMatch(/token|authorization/i);
  });
});
