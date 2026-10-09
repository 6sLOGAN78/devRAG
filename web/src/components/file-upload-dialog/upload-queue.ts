import axios from "axios";
import { ApiError } from "@/services/http";
import { fileKey, type RejectReason } from "./file-rules";

/**
 * The upload queue: a pure reducer for the rows, a small external store that applies it synchronously, and a runner
 * that keeps at most two uploads in flight and maps each server answer to a row state (UI-SPEC "Upload behaviour").
 * No React here; the dialog subscribes to the store.
 */

export type RowStatus = "rejected" | "ready" | "uploading" | "finishing" | "done" | "failed" | "cancelled";

/** Why a row failed. Server text (`message`) is shown as returned; the other kinds map to fixed copy. */
export type RowFailure =
  | { kind: "message"; text: string }
  | { kind: "rejected" }
  | { kind: "tooLarge" }
  | { kind: "limit" }
  | { kind: "network" }
  | { kind: "server" };

export type FatalState = "gone" | "forbidden";

export interface QueueRow {
  id: number;
  file: File;
  key: string;
  name: string;
  size: number;
  status: RowStatus;
  /** 0 to 99 while the request runs, 100 once the server has answered. */
  percent: number;
  /** True once the user asked for this row to be uploaded in the current run. */
  queued: boolean;
  /** The client check that refused the file, when status is `rejected`. */
  rejection: RejectReason | null;
  failure: RowFailure | null;
  /** The final name when the server renamed the file (D-14); null otherwise. */
  savedName: string | null;
}

export interface QueueState {
  rows: QueueRow[];
  fatal: FatalState | null;
  nextId: number;
}

export interface NewEntry {
  file: File;
  rejection: RejectReason | null;
}

export type QueueAction =
  | { type: "add"; entries: NewEntry[] }
  | { type: "remove"; id: number }
  | { type: "queue"; ids: number[] }
  | { type: "start"; id: number }
  | { type: "progress"; id: number; loaded: number; total: number | undefined }
  | { type: "done"; id: number; name: string }
  | { type: "fail"; id: number; failure: RowFailure }
  | { type: "failReady"; failure: RowFailure }
  | { type: "cancel"; id: number }
  | { type: "retry"; id: number }
  | { type: "stop" }
  | { type: "fatal"; kind: FatalState };

export const initialQueueState = (): QueueState => ({ rows: [], fatal: null, nextId: 1 });

const isRunning = (row: QueueRow) => row.status === "uploading" || row.status === "finishing";
const isWaiting = (row: QueueRow) => row.status === "ready" && row.queued;

/** A new run starts its counters from zero: when nothing is running or waiting, the old run's flags are dropped. */
function freshRun(rows: QueueRow[]): QueueRow[] {
  return rows.some((row) => isRunning(row) || isWaiting(row)) ? rows : rows.map((row) => (row.queued ? { ...row, queued: false } : row));
}

function mapRow(state: QueueState, id: number, change: (row: QueueRow) => QueueRow | null): QueueState {
  let changed = false;
  const rows = state.rows.map((row) => {
    if (row.id !== id) return row;
    const next = change(row);
    if (next === null || next === row) return row;
    changed = true;
    return next;
  });
  return changed ? { ...state, rows } : state;
}

export function queueReducer(state: QueueState, action: QueueAction): QueueState {
  switch (action.type) {
    case "add": {
      if (action.entries.length === 0) return state;
      let nextId = state.nextId;
      const added = action.entries.map(
        ({ file, rejection }): QueueRow => ({
          id: nextId++,
          file,
          key: fileKey(file),
          name: file.name,
          size: file.size,
          status: rejection === null ? "ready" : "rejected",
          percent: 0,
          queued: false,
          rejection,
          failure: null,
          savedName: null,
        }),
      );
      return { ...state, rows: [...state.rows, ...added], nextId };
    }
    case "remove": {
      const target = state.rows.find((row) => row.id === action.id);
      if (!target || isRunning(target)) return state;
      return { ...state, rows: state.rows.filter((row) => row.id !== action.id) };
    }
    case "queue": {
      const ids = new Set(action.ids);
      const rows = freshRun(state.rows).map((row) => (ids.has(row.id) && row.status === "ready" ? { ...row, queued: true } : row));
      return { ...state, rows };
    }
    case "start":
      return mapRow(state, action.id, (row) => (row.status === "ready" ? { ...row, status: "uploading", percent: 0 } : null));
    case "progress":
      return mapRow(state, action.id, (row) => {
        if (row.status !== "uploading" || action.total === undefined || !(action.total > 0)) return null;
        const percent = Math.max(row.percent, Math.min(99, Math.floor((action.loaded / action.total) * 100)));
        const allSent = action.loaded >= action.total;
        if (percent === row.percent && !allSent) return null;
        return { ...row, percent, status: allSent ? "finishing" : "uploading" };
      });
    case "done":
      return mapRow(state, action.id, (row) =>
        isRunning(row) ? { ...row, status: "done", percent: 100, failure: null, savedName: action.name !== "" && action.name !== row.name ? action.name : null } : null,
      );
    case "fail":
      return mapRow(state, action.id, (row) => (isRunning(row) || row.status === "ready" ? { ...row, status: "failed", failure: action.failure } : null));
    case "failReady": {
      if (!state.rows.some((row) => row.status === "ready")) return state;
      return { ...state, rows: state.rows.map((row) => (row.status === "ready" ? { ...row, status: "failed", failure: action.failure } : row)) };
    }
    case "cancel":
      return mapRow(state, action.id, (row) => (isRunning(row) || row.status === "ready" ? { ...row, status: "cancelled" } : null));
    case "retry":
      return mapRow({ ...state, rows: freshRun(state.rows) }, action.id, (row) =>
        row.status === "failed" || row.status === "cancelled" ? { ...row, status: "ready", percent: 0, queued: true, failure: null, savedName: null } : null,
      );
    case "stop": {
      if (!state.rows.some((row) => isRunning(row) || isWaiting(row))) return state;
      return { ...state, rows: state.rows.map((row) => (isRunning(row) || isWaiting(row) ? { ...row, status: "cancelled" } : row)) };
    }
    case "fatal": {
      const rows = state.rows.map((row) => (row.status === "ready" ? { ...row, status: "cancelled" as const } : row));
      return { ...state, rows, fatal: action.kind };
    }
    default:
      return state;
  }
}

export interface QueueCounts {
  ready: number;
  /** Uploading and Finishing. */
  uploading: number;
  done: number;
  failed: number;
  cancelled: number;
  rejected: number;
  /** Done rows the server renamed. */
  renamed: number;
  /** Rows in the current run. */
  queued: number;
  /** Rows of the current run that have finished one way or another. */
  queuedSettled: number;
  /** Rows still to finish: running ones plus the waiting rows of the current run. */
  pending: number;
  /** Rows that finished one way or another (done, failed, cancelled). */
  settled: number;
}

export function queueCounts(state: QueueState): QueueCounts {
  const counts: QueueCounts = { ready: 0, uploading: 0, done: 0, failed: 0, cancelled: 0, rejected: 0, renamed: 0, queued: 0, queuedSettled: 0, pending: 0, settled: 0 };
  for (const row of state.rows) {
    if (row.status === "ready") counts.ready += 1;
    else if (isRunning(row)) counts.uploading += 1;
    else if (row.status === "done") counts.done += 1;
    else if (row.status === "failed") counts.failed += 1;
    else if (row.status === "cancelled") counts.cancelled += 1;
    else counts.rejected += 1;
    const settled = row.status === "done" || row.status === "failed" || row.status === "cancelled";
    if (settled) counts.settled += 1;
    if (row.status === "done" && row.savedName !== null) counts.renamed += 1;
    if (row.queued) {
      counts.queued += 1;
      if (settled) counts.queuedSettled += 1;
    }
    if (isRunning(row) || isWaiting(row)) counts.pending += 1;
  }
  return counts;
}

export interface QueueStore {
  getState: () => QueueState;
  dispatch: (action: QueueAction) => void;
  subscribe: (listener: () => void) => () => void;
}

/** Holds the state and applies actions synchronously, so the runner always reads the result of its own dispatch. */
export function createQueueStore(initial: QueueState = initialQueueState()): QueueStore {
  let state = initial;
  const listeners = new Set<() => void>();
  return {
    getState: () => state,
    dispatch: (action) => {
      const next = queueReducer(state, action);
      if (next === state) return;
      state = next;
      for (const listener of [...listeners]) listener();
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
  };
}

export interface UploadCall {
  signal: AbortSignal;
  onProgress: (loaded: number, total: number | undefined) => void;
}

/** What an upload resolves to: the stored document, of which only the final name is read. */
export type UploadResult = Promise<{ name: string }>;

/** Uploads one file. */
export type UploadFn = (file: File, call: UploadCall) => UploadResult;

export type Outcome = "done" | "failed" | "cancelled";

export interface RunnerOptions {
  getState: () => QueueState;
  dispatch: (action: QueueAction) => void;
  upload: UploadFn;
  /** Uploads in flight at once. */
  concurrency?: number;
  /** Called after a request ends, whatever the outcome (the dialog refreshes the document list). */
  onSettled?: (outcome: Outcome) => void;
}

export interface Runner {
  /** Queues every Ready row and starts uploading. */
  start: () => void;
  /** Aborts one running upload; the row becomes Cancelled. */
  cancel: (id: number) => void;
  /** Re-queues a Failed or Cancelled row and uploads it. */
  retry: (id: number) => void;
  /** Aborts everything in flight and cancels what was waiting. */
  stop: () => void;
}

const MAX_SERVER_TEXT = 300;

type Verdict = { failure: RowFailure; limit: boolean } | { fatal: FatalState } | { stop: true };

/** Maps what the transport reported to a row failure, a dialog-level state, or the end of the session. */
function classify(error: unknown): Verdict {
  if (!(error instanceof ApiError)) return { failure: { kind: "server" }, limit: false };
  const data = error.data as { reason?: unknown } | null | undefined;
  const reason = typeof data?.reason === "string" ? data.reason : "";
  const message = error.message.trim().slice(0, MAX_SERVER_TEXT);
  if (error.status === 401) return { stop: true };
  if (error.status === 404) return { fatal: "gone" };
  if (error.status === 403) return { fatal: "forbidden" };
  if (error.status === 413) return { failure: { kind: "tooLarge" }, limit: false };
  if (error.status === 0) return { failure: { kind: "network" }, limit: false };
  if (error.status >= 500 || error.status === 408) return { failure: { kind: "server" }, limit: false };
  if (reason === "dataset_limit" || reason === "too_many_files") return { failure: message === "" ? { kind: "limit" } : { kind: "message", text: message }, limit: true };
  return { failure: message === "" ? { kind: "rejected" } : { kind: "message", text: message }, limit: false };
}

export function runQueue({ getState, dispatch, upload, concurrency = 2, onSettled }: RunnerOptions): Runner {
  const controllers = new Map<number, AbortController>();
  let halted = false;

  function settle(id: number, error: unknown, controller: AbortController): Outcome {
    if (controller.signal.aborted || axios.isCancel(error)) {
      dispatch({ type: "cancel", id });
      return "cancelled";
    }
    const verdict = classify(error);
    if ("fatal" in verdict) {
      halted = true;
      dispatch({ type: "cancel", id });
      dispatch({ type: "fatal", kind: verdict.fatal });
      return "failed";
    }
    if ("stop" in verdict) {
      stop();
      return "failed";
    }
    dispatch({ type: "fail", id, failure: verdict.failure });
    if (verdict.limit) dispatch({ type: "failReady", failure: verdict.failure });
    return "failed";
  }

  function launch(row: QueueRow): void {
    const controller = new AbortController();
    controllers.set(row.id, controller);
    dispatch({ type: "start", id: row.id });
    void upload(row.file, { signal: controller.signal, onProgress: (loaded, total) => dispatch({ type: "progress", id: row.id, loaded, total }) })
      .then(
        (document) => {
          if (controller.signal.aborted) return "cancelled" as const;
          dispatch({ type: "done", id: row.id, name: document.name });
          return "done" as const;
        },
        (error: unknown) => settle(row.id, error, controller),
      )
      .then((outcome) => {
        controllers.delete(row.id);
        onSettled?.(outcome);
        pump();
      });
  }

  function pump(): void {
    while (!halted && controllers.size < concurrency) {
      const next = getState().rows.find((row) => row.status === "ready" && row.queued);
      if (!next) return;
      launch(next);
    }
  }

  function stop(): void {
    halted = true;
    for (const controller of controllers.values()) controller.abort();
    dispatch({ type: "stop" });
  }

  return {
    start: () => {
      halted = false;
      dispatch({ type: "queue", ids: getState().rows.filter((row) => row.status === "ready").map((row) => row.id) });
      pump();
    },
    cancel: (id) => {
      const controller = controllers.get(id);
      if (!controller) return;
      controller.abort();
      dispatch({ type: "cancel", id });
    },
    retry: (id) => {
      halted = false;
      dispatch({ type: "retry", id });
      pump();
    },
    stop,
  };
}
