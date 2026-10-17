import { AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { checkEmbedding, getIngestionLog, getIngestionSummary, getTaskStatus, listIngestionLogs } from "./ingestion-service";
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

const logDto = {
  id: "l1",
  document_id: "d1",
  document_name: "a.pdf",
  started_at: 1700000000000,
  duration_seconds: 2.5,
  result: "partial",
  attempts: 2,
  max_attempts: 3,
  retried: true,
  chunk_count: 8,
  pages_total: 10,
  pages_without_text: 1,
  error: { step: "embed", code: "provider_refused", message: "no", detail: null, trace: "x" },
};

describe("ingestion reads (UI-19)", () => {
  it("maps the summary", async () => {
    body = success({ unstart: 1, running: 2, done: 3, failed: 4, cancelled: 5, partial: 6, chunk_total: 70, token_total: 800, extra: 1 });
    expect(await getIngestionSummary(D)).toEqual({ unstart: 1, running: 2, done: 3, failed: 4, cancelled: 5, partial: 6, chunkTotal: 70, tokenTotal: 800 });
    expect(seen[0]?.url).toBe(`/api/v1/datasets/${D}/ingestions/summary`);
    expect(seen[0]?.silent).toBe(true);
  });

  it("lists runs with the page size capped at 100 and maps every log field", async () => {
    body = success({ items: [logDto], total: 1 });
    const page = await listIngestionLogs(D, 1, 500);
    expect(seen[0]?.params).toEqual({ page: 1, size: 100 });
    expect(page.total).toBe(1);
    expect(page.items[0]).toEqual({
      id: "l1",
      documentId: "d1",
      documentName: "a.pdf",
      startedAt: 1700000000000,
      durationSeconds: 2.5,
      result: "partial",
      attempts: 2,
      maxAttempts: 3,
      retried: true,
      chunkCount: 8,
      pagesTotal: 10,
      pagesWithoutText: 1,
      error: { step: "embed", code: "provider_refused", message: "no", detail: null },
    });
  });

  it("keeps at most 3000 log lines and only strings", async () => {
    body = success({ ...logDto, error: null, log: ["a", 5, null, ...Array.from({ length: 3500 }, () => "x"), "y".repeat(5000)] });
    const detail = await getIngestionLog(D, "l/1");
    expect(seen[0]?.url).toBe(`/api/v1/datasets/${D}/ingestions/l%2F1`);
    expect(detail.log).toHaveLength(3000);
    expect(detail.log.every((line) => typeof line === "string")).toBe(true);
    expect(detail.error).toBeNull();
    body = success({ ...logDto, log: "not a list" });
    expect((await getIngestionLog(D, "l1")).log).toEqual([]);
  });

  it("maps a task and an embedding check", async () => {
    body = success({ id: "t1", doc_id: "d1", dataset_id: D, from_page: 0, to_page: 12, progress: 0.5, progress_message: "m".repeat(900), attempts: 1, finished: false, failed: false, error: null });
    const task = await getTaskStatus("t1");
    expect(seen[0]?.url).toBe("/v1/task/status/t1");
    expect(task).toMatchObject({ id: "t1", docId: "d1", toPage: 12, progress: 0.5, finished: false });
    expect(task.progressMessage).toHaveLength(300);
    seen = [];
    body = success({ ok: false, dimension: 768, expected: 1024 });
    expect(await checkEmbedding(D)).toEqual({ ok: false, dimension: 768, expected: 1024 });
    expect(JSON.parse(seen[0]?.data as string)).toEqual({ embd_id: null });
    expect(seen[0]?.method).toBe("post");
    expect(seen[0]?.silent).toBe(true);
  });
});
