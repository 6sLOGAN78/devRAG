import type { AreaHandler, DatasetServer } from "../dataset-server";
import { fileExtraOf, fileLogsOf, type LogRow } from "./files";

/**
 * Test-server area for the parsing log (R-167): `GET .../ingestions` (newest first, paged) and `GET .../ingestions/{id}`.
 * The rows come from the log rows the `files` area keeps; what a row does not carry (lines, attempts, start time, its own
 * error) is set per log with `setLogExtra`. Fake data only.
 */

export interface LogExtra {
  lines?: string[];
  startedAt?: number;
  durationSeconds?: number;
  attempts?: number;
  maxAttempts?: number;
  retried?: boolean;
  /** Overrides the error the document carries, so an older run keeps its own reason. */
  error?: { step: string; code: string; message: string; detail?: string | null } | null;
  chunkCount?: number;
}

const BASE_TIME = 1_700_000_000_000;

interface LogsState {
  extras: Record<string, LogExtra>;
}

const stateOf = (server: DatasetServer): LogsState => server.areaState<LogsState>("ingestion-logs", () => ({ extras: {} }));

/** Sets the fields of one log entry that the shared rows do not carry. */
export function setLogExtra(server: DatasetServer, logId: string, extra: LogExtra): void {
  const state = stateOf(server);
  state.extras[logId] = { ...state.extras[logId], ...extra };
}

/** Replaces the lines of a log entry, as a worker appending progress would. */
export function appendLogLines(server: DatasetServer, logId: string, lines: string[]): void {
  const current = stateOf(server).extras[logId]?.lines ?? [];
  setLogExtra(server, logId, { lines: [...current, ...lines] });
}

function findDocument(server: DatasetServer, docId: string) {
  for (const list of Object.values(server.documents)) {
    const row = list.find((d) => d.id === docId);
    if (row) return row;
  }
  return undefined;
}

function viewOf(server: DatasetServer, row: LogRow, index: number) {
  const extra = stateOf(server).extras[row.id] ?? {};
  const document = findDocument(server, row.docId);
  const own = fileExtraOf(server, row.docId);
  const error = extra.error !== undefined ? extra.error : row.result === "failed" ? (own.error ?? null) : null;
  return {
    id: row.id,
    document_id: row.docId,
    document_name: document?.name ?? "removed.pdf",
    started_at: extra.startedAt ?? BASE_TIME + index * 60_000,
    duration_seconds: extra.durationSeconds ?? 3.2,
    result: row.result,
    attempts: extra.attempts ?? 1,
    max_attempts: extra.maxAttempts ?? 3,
    retried: extra.retried ?? false,
    chunk_count: extra.chunkCount ?? document?.chunk_num ?? 0,
    pages_total: own.pagesTotal ?? null,
    pages_without_text: own.pagesWithoutText ?? null,
    error: error === null ? null : { detail: null, ...error },
  };
}

const LOG_ROUTE = /^\/api\/v1\/datasets\/([^/]+)\/ingestions(?:\/([^/]+))?$/;

export const handle: AreaHandler = ({ server, method, url, params, ok, failure }) => {
  const matched = LOG_ROUTE.exec(url);
  if (!matched || method !== "GET") return undefined;
  const datasetId = matched[1] as string;
  const logId = matched[2];
  if (logId === "summary" || !server.datasets[datasetId]) return undefined;
  const ownDocs = new Set((server.documents[datasetId] ?? []).map((d) => d.id));
  const all = fileLogsOf(server)
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => ownDocs.has(row.docId));

  if (logId === undefined) {
    const size = Number(params.size);
    const page = Number(params.page);
    const newest = [...all].reverse();
    return ok({ items: newest.slice((page - 1) * size, page * size).map(({ row, index }) => viewOf(server, row, index)), total: newest.length });
  }
  const found = all.find(({ row }) => row.id === logId);
  if (!found) return failure({ status: 404, message: "not_found", reason: "not_found" });
  return ok({ ...viewOf(server, found.row, found.index), log: stateOf(server).extras[logId]?.lines ?? [] });
};
