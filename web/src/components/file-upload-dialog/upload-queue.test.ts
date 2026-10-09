import { CanceledError } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/http";
import { createQueueStore, queueCounts, runQueue, type QueueRow, type UploadFn } from "./upload-queue";

const file = (name: string, size = 10) => new File([new Uint8Array(size)], name, { lastModified: 1 });

interface Call {
  file: File;
  signal: AbortSignal;
  onProgress: (loaded: number, total: number | undefined) => void;
  resolve: (doc: { name: string }) => void;
  reject: (error: unknown) => void;
}
let calls: Call[] = [];

const upload: UploadFn = (f, options) =>
  new Promise((resolve, reject) => {
    calls.push({ file: f, signal: options.signal, onProgress: options.onProgress, resolve, reject });
    options.signal.addEventListener("abort", () => reject(new CanceledError()));
  });

/** Lets the runner's promise handlers run; microtasks only, no timers. */
const flush = async () => {
  for (let i = 0; i < 8; i += 1) await Promise.resolve();
};

function setup(names: string[], concurrency?: number) {
  const store = createQueueStore();
  const onSettled = vi.fn();
  const runner = runQueue({ getState: store.getState, dispatch: store.dispatch, upload, onSettled, ...(concurrency ? { concurrency } : {}) });
  store.dispatch({ type: "add", entries: names.map((name) => ({ file: file(name), rejection: null })) });
  return { store, runner, onSettled };
}

const row = (store: ReturnType<typeof createQueueStore>, name: string): QueueRow => {
  const found = store.getState().rows.find((r) => r.name === name);
  if (!found) throw new Error(`no row ${name}`);
  return found;
};
const api = (status: number, message: string, reason?: string) => new ApiError({ code: status, message, status, data: reason ? { reason } : null });

beforeEach(() => {
  calls = [];
});

describe("queue reducer", () => {
  it("adds ready rows and rejected rows with their own ids and sizes", () => {
    const store = createQueueStore();
    store.dispatch({ type: "add", entries: [{ file: file("a.pdf", 5), rejection: null }, { file: file("b.exe"), rejection: "extension" }] });
    const [a, b] = store.getState().rows;
    expect(a).toMatchObject({ name: "a.pdf", size: 5, status: "ready", rejection: null, percent: 0, queued: false });
    expect(b).toMatchObject({ name: "b.exe", status: "rejected", rejection: "extension" });
    expect(a?.id).not.toBe(b?.id);
  });

  it("removes a ready or rejected row but not one that is uploading", () => {
    const { store, runner } = setup(["a.pdf", "b.exe"]);
    store.dispatch({ type: "remove", id: row(store, "b.exe").id });
    expect(store.getState().rows.map((r) => r.name)).toEqual(["a.pdf"]);
    runner.start();
    store.dispatch({ type: "remove", id: row(store, "a.pdf").id });
    expect(row(store, "a.pdf").status).toBe("uploading");
  });

  it("returns the same state object for an action that changes nothing", () => {
    const store = createQueueStore();
    const before = store.getState();
    store.dispatch({ type: "remove", id: 99 });
    store.dispatch({ type: "progress", id: 99, loaded: 1, total: 2 });
    expect(store.getState()).toBe(before);
  });

  it("tells subscribers about a change and stops after unsubscribe", () => {
    const store = createQueueStore();
    const listener = vi.fn();
    const off = store.subscribe(listener);
    store.dispatch({ type: "add", entries: [{ file: file("a.pdf"), rejection: null }] });
    expect(listener).toHaveBeenCalledTimes(1);
    off();
    store.dispatch({ type: "add", entries: [{ file: file("b.pdf"), rejection: null }] });
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe("runner: concurrency and progress (UI-SPEC upload behaviour)", () => {
  it("starts nothing until start() is called", () => {
    setup(["a.pdf"]);
    expect(calls).toHaveLength(0);
  });

  it("has at most two uploads in flight and starts the next as one finishes", async () => {
    const { store, runner } = setup(["a.pdf", "b.pdf", "c.pdf", "d.pdf", "e.pdf"]);
    runner.start();
    expect(calls.map((c) => c.file.name)).toEqual(["a.pdf", "b.pdf"]);
    calls[0]!.resolve({ name: "a.pdf" });
    await flush();
    expect(calls.map((c) => c.file.name)).toEqual(["a.pdf", "b.pdf", "c.pdf"]);
    expect(queueCounts(store.getState()).uploading).toBe(2);
    calls[1]!.resolve({ name: "b.pdf" });
    calls[2]!.resolve({ name: "c.pdf" });
    await flush();
    expect(calls).toHaveLength(5);
  });

  it("gives every request its own AbortSignal", () => {
    const { runner } = setup(["a.pdf", "b.pdf"]);
    runner.start();
    expect(calls[0]!.signal).not.toBe(calls[1]!.signal);
    expect(calls[0]!.signal.aborted).toBe(false);
  });

  it("caps progress at 99 and moves to Finishing when every byte is sent", () => {
    const { store, runner } = setup(["a.pdf"]);
    runner.start();
    calls[0]!.onProgress(50, 100);
    expect(row(store, "a.pdf")).toMatchObject({ status: "uploading", percent: 50 });
    calls[0]!.onProgress(999, 1000);
    expect(row(store, "a.pdf")).toMatchObject({ status: "uploading", percent: 99 });
    calls[0]!.onProgress(1000, 1000);
    expect(row(store, "a.pdf")).toMatchObject({ status: "finishing", percent: 99 });
  });

  it("never lets progress go backwards and ignores a report without a total", () => {
    const { store, runner } = setup(["a.pdf"]);
    runner.start();
    calls[0]!.onProgress(60, 100);
    calls[0]!.onProgress(30, 100);
    calls[0]!.onProgress(10, undefined);
    expect(row(store, "a.pdf").percent).toBe(60);
  });

  it("starts only the rows that were queued, not ones added later", async () => {
    const { store, runner } = setup(["a.pdf"]);
    runner.start();
    store.dispatch({ type: "add", entries: [{ file: file("late.pdf"), rejection: null }] });
    calls[0]!.resolve({ name: "a.pdf" });
    await flush();
    expect(calls).toHaveLength(1);
    expect(row(store, "late.pdf").status).toBe("ready");
    runner.start();
    expect(calls).toHaveLength(2);
  });

  it("never starts a row that was removed while it waited", async () => {
    const { store, runner } = setup(["a.pdf", "b.pdf", "c.pdf"], 1);
    runner.start();
    expect(calls).toHaveLength(1);
    store.dispatch({ type: "remove", id: row(store, "b.pdf").id });
    calls[0]!.resolve({ name: "a.pdf" });
    await flush();
    expect(calls.map((c) => c.file.name)).toEqual(["a.pdf", "c.pdf"]);
  });
});

describe("runner: results (D-14 and the server-answer table)", () => {
  it("marks a done row, and a renamed one when the server's name differs (D-14)", async () => {
    const { store, runner, onSettled } = setup(["report.pdf", "plain.pdf"]);
    runner.start();
    calls[0]!.resolve({ name: "report(1).pdf" });
    calls[1]!.resolve({ name: "plain.pdf" });
    await flush();
    expect(row(store, "report.pdf")).toMatchObject({ status: "done", percent: 100, savedName: "report(1).pdf" });
    expect(row(store, "plain.pdf")).toMatchObject({ status: "done", savedName: null });
    expect(onSettled).toHaveBeenCalledWith("done");
  });

  it("ignores a late progress report after the row is done", async () => {
    const { store, runner } = setup(["a.pdf"]);
    runner.start();
    calls[0]!.resolve({ name: "a.pdf" });
    await flush();
    calls[0]!.onProgress(10, 100);
    expect(row(store, "a.pdf")).toMatchObject({ status: "done", percent: 100 });
  });

  it("HTTP 400 fails the row with the server message and the queue continues", async () => {
    const { store, runner } = setup(["a.pdf", "b.pdf", "c.pdf"]);
    runner.start();
    calls[0]!.reject(api(400, "unsupported file type", "unsupported_type"));
    await flush();
    expect(row(store, "a.pdf")).toMatchObject({ status: "failed", failure: { kind: "message", text: "unsupported file type" } });
    expect(calls).toHaveLength(3);
  });

  it("HTTP 400 without a message uses the generic refusal", async () => {
    const { store, runner } = setup(["a.pdf"]);
    runner.start();
    calls[0]!.reject(api(400, ""));
    await flush();
    expect(row(store, "a.pdf").failure).toEqual({ kind: "rejected" });
  });

  it("HTTP 413 fails with the size message, including Nginx's answer that carries no reason", async () => {
    const { store, runner } = setup(["a.pdf", "b.pdf"]);
    runner.start();
    calls[0]!.reject(api(413, "payload too large"));
    calls[1]!.reject(api(413, "file too large", "file_too_large"));
    await flush();
    expect(row(store, "a.pdf").failure).toEqual({ kind: "tooLarge" });
    expect(row(store, "b.pdf").failure).toEqual({ kind: "tooLarge" });
  });

  it.each(["dataset_limit", "too_many_files"])("reason %s fails every remaining ready row with the same message", async (reason) => {
    const { store, runner } = setup(["a.pdf", "b.pdf", "c.pdf", "d.pdf"]);
    runner.start();
    calls[0]!.reject(api(400, "dataset is full", reason));
    await flush();
    expect(row(store, "a.pdf").failure).toEqual({ kind: "message", text: "dataset is full" });
    expect(row(store, "c.pdf")).toMatchObject({ status: "failed", failure: { kind: "message", text: "dataset is full" } });
    expect(row(store, "d.pdf").status).toBe("failed");
    expect(row(store, "b.pdf").status).toBe("uploading");
    expect(calls).toHaveLength(2);
  });

  it("a limit answer without text uses the limit fallback", async () => {
    const { store, runner } = setup(["a.pdf", "b.pdf", "c.pdf"]);
    runner.start();
    calls[0]!.reject(api(400, "", "dataset_limit"));
    await flush();
    expect(row(store, "c.pdf").failure).toEqual({ kind: "limit" });
  });

  it("HTTP 404 stops the queue, cancels the ready rows and raises the gone state", async () => {
    const { store, runner } = setup(["a.pdf", "b.pdf", "c.pdf"]);
    runner.start();
    calls[0]!.reject(api(404, "not found"));
    await flush();
    expect(store.getState().fatal).toBe("gone");
    expect(row(store, "c.pdf").status).toBe("cancelled");
    calls[1]!.resolve({ name: "b.pdf" });
    await flush();
    expect(calls).toHaveLength(2);
    expect(row(store, "c.pdf").status).toBe("cancelled");
  });

  it("HTTP 403 stops the queue with the forbidden state", async () => {
    const { store, runner } = setup(["a.pdf", "b.pdf", "c.pdf"]);
    runner.start();
    calls[0]!.reject(api(403, "forbidden"));
    await flush();
    expect(store.getState().fatal).toBe("forbidden");
    expect(row(store, "c.pdf").status).toBe("cancelled");
  });

  it("a network failure and an expired timeout (status 0) fail with the connection message", async () => {
    const { store, runner } = setup(["a.pdf", "b.pdf", "c.pdf"]);
    runner.start();
    calls[0]!.reject(new ApiError({ code: -1, status: 0, message: "Network error" }));
    await flush();
    expect(row(store, "a.pdf")).toMatchObject({ status: "failed", failure: { kind: "network" } });
    expect(calls).toHaveLength(3);
  });

  it.each([500, 502, 503, 504, 408])("HTTP %s fails with the retryable server message", async (status) => {
    const { store, runner } = setup(["a.pdf"]);
    runner.start();
    calls[0]!.reject(api(status, "boom", "busy"));
    await flush();
    expect(row(store, "a.pdf").failure).toEqual({ kind: "server" });
  });

  it("a failure that is not an ApiError is shown as the server message", async () => {
    const { store, runner } = setup(["a.pdf"]);
    runner.start();
    calls[0]!.reject(new TypeError("x"));
    await flush();
    expect(row(store, "a.pdf").failure).toEqual({ kind: "server" });
  });

  it("a real 401 stops the queue without a message of its own (the shared session flow handles it)", async () => {
    const { store, runner } = setup(["a.pdf", "b.pdf", "c.pdf"]);
    runner.start();
    calls[0]!.reject(api(401, "unauthorized"));
    await flush();
    expect(store.getState().fatal).toBeNull();
    expect(row(store, "a.pdf").status).toBe("cancelled");
    expect(row(store, "c.pdf").status).toBe("cancelled");
    expect(calls).toHaveLength(2);
  });
});

describe("runner: cancel, retry and stop", () => {
  it("cancel aborts the request, marks the row Cancelled and frees the slot", async () => {
    const { store, runner, onSettled } = setup(["a.pdf", "b.pdf", "c.pdf"]);
    runner.start();
    runner.cancel(row(store, "a.pdf").id);
    await flush();
    expect(calls[0]!.signal.aborted).toBe(true);
    expect(row(store, "a.pdf").status).toBe("cancelled");
    expect(calls).toHaveLength(3);
    expect(onSettled).toHaveBeenCalledWith("cancelled");
  });

  it("an abort that the transport reports later does not turn Cancelled into Failed", async () => {
    const { store, runner } = setup(["a.pdf"]);
    runner.start();
    runner.cancel(row(store, "a.pdf").id);
    calls[0]!.reject(api(500, "late"));
    await flush();
    expect(row(store, "a.pdf").status).toBe("cancelled");
  });

  it("retry re-queues a failed row and uploads it again", async () => {
    const { store, runner } = setup(["a.pdf"]);
    runner.start();
    calls[0]!.reject(api(500, "boom"));
    await flush();
    expect(row(store, "a.pdf").status).toBe("failed");
    runner.retry(row(store, "a.pdf").id);
    expect(calls).toHaveLength(2);
    expect(row(store, "a.pdf")).toMatchObject({ status: "uploading", failure: null, percent: 0 });
    calls[1]!.resolve({ name: "a.pdf" });
    await flush();
    expect(row(store, "a.pdf").status).toBe("done");
  });

  it("retry also works for a Cancelled row", async () => {
    const { store, runner } = setup(["a.pdf"]);
    runner.start();
    runner.cancel(row(store, "a.pdf").id);
    runner.retry(row(store, "a.pdf").id);
    expect(calls).toHaveLength(2);
    expect(calls[1]!.signal.aborted).toBe(false);
  });

  it("stop aborts every request and cancels the queued rows that never started", async () => {
    const { store, runner } = setup(["a.pdf", "b.pdf", "c.pdf"]);
    runner.start();
    runner.stop();
    await flush();
    expect(calls.map((c) => c.signal.aborted)).toEqual([true, true]);
    expect(store.getState().rows.map((r) => r.status)).toEqual(["cancelled", "cancelled", "cancelled"]);
    expect(calls).toHaveLength(2);
  });

  it("can start again after stop (a remounted dialog reuses the runner)", () => {
    const { store, runner } = setup([]);
    runner.stop();
    store.dispatch({ type: "add", entries: [{ file: file("b.pdf"), rejection: null }] });
    runner.start();
    expect(calls.map((c) => c.file.name)).toEqual(["b.pdf"]);
  });
});

describe("queueCounts", () => {
  it("counts rows by state and tells what is pending and what has settled", async () => {
    const { store, runner } = setup(["a.pdf", "b.pdf", "c.pdf", "d.pdf"], 1);
    store.dispatch({ type: "add", entries: [{ file: file("x.exe"), rejection: "extension" }] });
    expect(queueCounts(store.getState())).toMatchObject({ ready: 4, rejected: 1, uploading: 0, pending: 0, settled: 0 });
    runner.start();
    expect(queueCounts(store.getState())).toMatchObject({ ready: 3, uploading: 1, pending: 4, queued: 4, settled: 0 });
    calls[0]!.resolve({ name: "a(1).pdf" });
    await flush();
    calls[1]!.reject(api(400, "no"));
    await flush();
    expect(queueCounts(store.getState())).toMatchObject({ done: 1, failed: 1, renamed: 1, uploading: 1, ready: 1, settled: 2, queued: 4 });
  });

  it("starts a new run's counters from zero once the previous run is over", async () => {
    const { store, runner } = setup(["a.pdf"]);
    runner.start();
    calls[0]!.resolve({ name: "a.pdf" });
    await flush();
    store.dispatch({ type: "add", entries: [{ file: file("b.pdf"), rejection: null }] });
    runner.start();
    expect(queueCounts(store.getState())).toMatchObject({ queued: 1, settled: 1, done: 1 });
    expect(queueCounts(store.getState()).queuedSettled).toBe(0);
  });
});
