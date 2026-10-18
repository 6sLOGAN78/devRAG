import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from "axios";
import type { AreaHandler, DatasetServer, DocumentRow } from "../dataset-server";

/**
 * Test-server area for the document table of Phase 4 (R-167): the document list with the Phase 4 row fields, parse and
 * cancel with the server's confirmation rule, the search switch, the ingestion summary and the document detail. Its
 * state lives in `server.areaState("files", ...)`, so a reset clears it. Fake data only.
 */

export interface FileExtra {
  parseable?: boolean;
  enabled?: boolean;
  thumbnail?: string | null;
  tokenNum?: number;
  /** Chunks the reader edited, and chunks added by hand (they decide the re-parse confirmation). */
  editedCount?: number;
  manualCount?: number;
  progressMessage?: string;
  error?: { step: string; code: string; message: string } | null;
  pagesTotal?: number | null;
  pagesWithoutText?: number | null;
  /** The next replacing parse is refused once more with fresh counts, as when the chunks changed meanwhile. */
  refuseConfirmOnce?: boolean;
}

export interface LogRow {
  id: string;
  docId: string;
  result: "running" | "done" | "failed" | "cancelled";
}

interface FilesState {
  extras: Record<string, FileExtra>;
  logs: LogRow[];
  lastLog: Record<string, string>;
  counter: number;
}

const stateOf = (server: DatasetServer): FilesState => server.areaState<FilesState>("files", () => ({ extras: {}, logs: [], lastLog: {}, counter: 0 }));

/** Sets fields a document row of the shared server does not carry (switch, thumbnail, edits, message, error). */
export function setFileExtra(server: DatasetServer, docId: string, extra: FileExtra): void {
  const state = stateOf(server);
  state.extras[docId] = { ...state.extras[docId], ...extra };
}

export const fileLogsOf = (server: DatasetServer): readonly LogRow[] => stateOf(server).logs;

function findDocument(server: DatasetServer, docId: string): DocumentRow | undefined {
  for (const list of Object.values(server.documents)) {
    const row = list.find((d) => d.id === docId);
    if (row) return row;
  }
  return undefined;
}

export interface ParseStep {
  run: "0" | "1" | "2" | "3" | "4";
  progress?: number;
  chunkCount?: number;
  message?: string;
  error?: FileExtra["error"];
}

/** Moves a document on as a worker would and closes its log row when it leaves running. Test helper. */
export function advanceParse(server: DatasetServer, docId: string, step: ParseStep): void {
  const row = findDocument(server, docId);
  if (!row) throw new Error(`no document ${docId}`);
  const state = stateOf(server);
  row.run = step.run;
  if (step.progress !== undefined) row.progress = step.progress;
  if (step.chunkCount !== undefined) row.chunk_num = step.chunkCount;
  const extra = (state.extras[docId] ??= {});
  if (step.message !== undefined) extra.progressMessage = step.message;
  if (step.error !== undefined) extra.error = step.error;
  const log = state.logs.find((l) => l.id === state.lastLog[docId]);
  if (log && step.run !== "1") log.result = step.run === "3" ? "done" : step.run === "2" ? "cancelled" : "failed";
}

function refuse(config: InternalAxiosRequestConfig, status: number, reason: string, extra: Record<string, unknown> = {}): Promise<never> {
  const body = { code: status, message: reason, data: { reason, ...extra } };
  const response = { data: body, status, statusText: String(status), headers: new AxiosHeaders(), config } as never;
  return Promise.reject(new AxiosError(`status ${status}`, "ERR_BAD_RESPONSE", config, null, response));
}

const viewOf = (row: DocumentRow, state: FilesState) => {
  const extra = state.extras[row.id] ?? {};
  return {
    ...row,
    chunk_count: row.chunk_num,
    token_num: extra.tokenNum ?? 0,
    parseable: extra.parseable ?? true,
    enabled: extra.enabled ?? true,
    thumbnail: extra.thumbnail ?? null,
    last_log_id: state.lastLog[row.id] ?? null,
    pages_total: extra.pagesTotal ?? null,
    pages_without_text: extra.pagesWithoutText ?? null,
    progress_message: extra.progressMessage ?? "",
    error: extra.error ?? null,
  };
};

const DATASET_ROUTE = /^\/api\/v1\/datasets\/([^/]+)\/(.+)$/;

function bodyOf(config: InternalAxiosRequestConfig): Record<string, unknown> {
  try {
    return JSON.parse(String(config.data)) as Record<string, unknown>;
  } catch {
    return {};
  }
}

const DATASET_DETAIL = /^\/api\/v1\/datasets\/([^/]+)$/;

export const handle: AreaHandler = ({ server, config, method, url, params, ok }) => {
  // The dataset detail follows the documents, so the page's chunk count moves with a parse like the real one does.
  const detail = DATASET_DETAIL.exec(url);
  if (detail && method === "GET") {
    const row = server.datasets[detail[1] as string];
    if (!row) return undefined;
    const own = server.documents[row.id] ?? [];
    const tokens = own.reduce((total, d) => total + (stateOf(server).extras[d.id]?.tokenNum ?? 0), 0);
    return ok({
      ...row,
      doc_num: own.length,
      chunk_num: own.reduce((total, d) => total + d.chunk_num, 0),
      token_num: tokens,
      language: "English",
      parser_id: "naive",
      create_time: row.update_time,
    });
  }
  const matched = DATASET_ROUTE.exec(url);
  if (!matched) return undefined;
  const datasetId = matched[1] as string;
  const rest = matched[2] as string;
  const state = stateOf(server);
  const dataset = server.datasets[datasetId];
  if (!dataset) return undefined;
  const list = (server.documents[datasetId] ??= []);

  if (method === "GET" && rest === "documents") {
    const keywords = String(params.keywords ?? "").toLowerCase();
    const matching = list.filter((d) => d.name.toLowerCase().includes(keywords));
    const size = Number(params.page_size);
    const page = Number(params.page);
    return ok({ items: matching.slice((page - 1) * size, page * size).map((d) => viewOf(d, state)), total: matching.length });
  }

  if (method === "GET" && rest === "ingestions/summary") {
    const summary = { unstart: 0, running: 0, done: 0, failed: 0, cancelled: 0, partial: 0, chunk_total: 0, token_total: 0 };
    for (const d of list) {
      if (d.run === "0") summary.unstart += 1;
      else if (d.run === "1") summary.running += 1;
      else if (d.run === "3") summary.done += 1;
      else if (d.run === "4") summary.failed += 1;
      else if (d.run === "2") summary.cancelled += 1;
      if ((d.run === "4" || d.run === "2") && d.chunk_num > 0) summary.partial += 1;
      summary.chunk_total += d.chunk_num;
      summary.token_total += state.extras[d.id]?.tokenNum ?? 0;
    }
    return ok(summary);
  }

  if (method === "POST" && rest === "documents/parse") {
    const sent = bodyOf(config);
    const ids = Array.isArray(sent.doc_ids) ? (sent.doc_ids as string[]) : [];
    const rows = ids.map((id) => list.find((d) => d.id === id));
    if (rows.some((r) => r === undefined)) return refuse(config, 404, "not_found");
    const found = rows as DocumentRow[];
    if (sent.run === "2") {
      for (const row of found) advanceParse(server, row.id, { run: "2" });
      return ok({ cancelled: ids });
    }
    for (const row of found) {
      if ((state.extras[row.id]?.parseable ?? true) === false) return refuse(config, 400, "parse_unavailable");
      if (row.run === "1") return refuse(config, 409, "already_running");
    }
    // A finished document, or any document with edited or hand-added chunks, needs the reader's say-so before its chunks go.
    const needing = found.filter((row) => {
      if (row.chunk_num <= 0) return false;
      const extra = state.extras[row.id] ?? {};
      return row.run === "3" || (extra.editedCount ?? 0) + (extra.manualCount ?? 0) > 0;
    });
    const stale = sent.confirm_replace === true ? found.filter((row) => state.extras[row.id]?.refuseConfirmOnce === true) : [];
    for (const row of stale) (state.extras[row.id] as FileExtra).refuseConfirmOnce = false;
    if (stale.length > 0 || (needing.length > 0 && sent.confirm_replace !== true)) {
      const documents = [...new Set([...needing, ...stale])].map((row) => ({
        id: row.id,
        name: row.name,
        chunk_count: row.chunk_num,
        edited_count: state.extras[row.id]?.editedCount ?? 0,
        manual_count: state.extras[row.id]?.manualCount ?? 0,
      }));
      return refuse(config, 409, "confirm_required", { documents });
    }
    for (const row of found) {
      state.counter += 1;
      const logId = `log${String(state.counter).padStart(29, "0")}`;
      state.logs.push({ id: logId, docId: row.id, result: "running" });
      state.lastLog[row.id] = logId;
      row.run = "1";
      row.progress = 0;
      row.chunk_num = 0;
      const extra = (state.extras[row.id] ??= {});
      extra.progressMessage = "";
      extra.error = null;
      extra.editedCount = 0;
      extra.manualCount = 0;
    }
    return ok({ started: ids });
  }

  if (method === "POST" && rest === "documents/batch-update-status") {
    const sent = bodyOf(config);
    const ids = Array.isArray(sent.doc_ids) ? (sent.doc_ids as string[]) : [];
    const enabled = sent.status === "1";
    for (const id of ids) setFileExtra(server, id, { enabled });
    return ok({ updated: ids, enabled });
  }

  const one = /^documents\/([^/]+)$/.exec(rest);
  if (method === "GET" && one) {
    const row = list.find((d) => d.id === one[1]);
    if (!row) return refuse(config, 404, "not_found");
    return ok({ ...viewOf(row, state), chunk_token_num: 512, delimiter: "\\n", overlapped_percent: 0, preview: "none" });
  }
  return undefined;
};
