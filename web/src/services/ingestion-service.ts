import { embeddingCheckPath, ingestionLogPath, ingestionLogsPath, ingestionSummaryPath, taskStatusPath } from "@/constants/api-paths";
import { request } from "./http";
import { asRecord, clampWhole, count, text } from "./mapping";

/**
 * Ingestion read APIs (plan 04-19). Server messages are fixed plain sentences, but they are still bounded and rendered
 * as text nodes only. Mappers copy an explicit field list.
 */

export interface IngestionSummary {
  unstart: number;
  running: number;
  done: number;
  failed: number;
  cancelled: number;
  partial: number;
  chunkTotal: number;
  tokenTotal: number;
}

export interface IngestionError {
  step: string;
  code: string;
  message: string;
  detail: string | null;
}

export interface IngestionLogView {
  id: string;
  documentId: string;
  documentName: string;
  startedAt: number;
  durationSeconds: number;
  result: string;
  attempts: number;
  maxAttempts: number;
  retried: boolean;
  chunkCount: number;
  pagesTotal: number | null;
  pagesWithoutText: number | null;
  error: IngestionError | null;
}

export interface IngestionLogDetail extends IngestionLogView {
  log: string[];
}

export interface IngestionLogPage {
  items: IngestionLogView[];
  total: number;
}

export interface TaskStatusView {
  id: string;
  docId: string;
  datasetId: string;
  fromPage: number;
  toPage: number;
  progress: number;
  progressMessage: string;
  attempts: number;
  finished: boolean;
  failed: boolean;
  error: IngestionError | null;
}

export interface EmbeddingCheckView {
  ok: boolean;
  dimension: number;
  expected: number;
}

export const MAX_LOG_PAGE_SIZE = 100;
export const MAX_LOG_LINES = 3000;
export const MAX_LOG_LINE_LENGTH = 1000;
export const MAX_MESSAGE_LENGTH = 300;
/** The embedding check calls the provider (30 s). */
export const EMBEDDING_CHECK_TIMEOUT_MS = 30000;

const optionalCount = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);

function toError(raw: unknown): IngestionError | null {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const dto = raw as Record<string, unknown>;
  return {
    step: text(dto.step),
    code: text(dto.code),
    // One character past the limit is kept, so a message that is too long stays detectable and is never shown cut (D-08).
    message: text(dto.message).slice(0, MAX_MESSAGE_LENGTH + 1),
    detail: typeof dto.detail === "string" ? dto.detail.slice(0, MAX_MESSAGE_LENGTH) : null,
  };
}

function toLog(raw: unknown): IngestionLogView {
  const dto = asRecord(raw);
  return {
    id: text(dto.id),
    documentId: text(dto.document_id),
    documentName: text(dto.document_name),
    startedAt: count(dto.started_at),
    durationSeconds: count(dto.duration_seconds),
    result: text(dto.result),
    attempts: count(dto.attempts),
    maxAttempts: count(dto.max_attempts),
    retried: dto.retried === true,
    chunkCount: count(dto.chunk_count),
    pagesTotal: optionalCount(dto.pages_total),
    pagesWithoutText: optionalCount(dto.pages_without_text),
    error: toError(dto.error),
  };
}

/** GET .../ingestions/summary. Silent: the strip renders its own failure. */
export async function getIngestionSummary(datasetId: string): Promise<IngestionSummary> {
  const dto = asRecord(await request<unknown>({ url: ingestionSummaryPath(datasetId), method: "GET" }, { silent: true }));
  return {
    unstart: count(dto.unstart),
    running: count(dto.running),
    done: count(dto.done),
    failed: count(dto.failed),
    cancelled: count(dto.cancelled),
    partial: count(dto.partial),
    chunkTotal: count(dto.chunk_total),
    tokenTotal: count(dto.token_total),
  };
}

/** GET .../ingestions: one page of runs, newest first; the page size is at most 100. */
export async function listIngestionLogs(datasetId: string, page: number, size: number): Promise<IngestionLogPage> {
  const params = { page: clampWhole(page, 1, Number.MAX_SAFE_INTEGER), size: clampWhole(size, 1, MAX_LOG_PAGE_SIZE) };
  const data = asRecord(await request<unknown>({ url: ingestionLogsPath(datasetId), method: "GET", params }, { silent: true }));
  return { items: Array.isArray(data.items) ? data.items.map(toLog) : [], total: count(data.total) };
}

/** GET .../ingestions/{id}: one run with its log lines (at most 3000, each a bounded string). */
export async function getIngestionLog(datasetId: string, logId: string): Promise<IngestionLogDetail> {
  const dto = asRecord(await request<unknown>({ url: ingestionLogPath(datasetId, logId), method: "GET" }, { silent: true }));
  const lines = Array.isArray(dto.log) ? dto.log.filter((line): line is string => typeof line === "string").slice(0, MAX_LOG_LINES) : [];
  return { ...toLog(dto), log: lines.map((line) => line.slice(0, MAX_LOG_LINE_LENGTH)) };
}

/** GET /v1/task/status/{id}. Silent: the caller polls. */
export async function getTaskStatus(taskId: string): Promise<TaskStatusView> {
  const dto = asRecord(await request<unknown>({ url: taskStatusPath(taskId), method: "GET" }, { silent: true }));
  return {
    id: text(dto.id),
    docId: text(dto.doc_id),
    datasetId: text(dto.dataset_id),
    fromPage: count(dto.from_page),
    toPage: count(dto.to_page),
    progress: count(dto.progress),
    progressMessage: text(dto.progress_message).slice(0, MAX_MESSAGE_LENGTH),
    attempts: count(dto.attempts),
    finished: dto.finished === true,
    failed: dto.failed === true,
    error: toError(dto.error),
  };
}

/**
 * POST .../embedding/check: tests the model against the dimension the index was built for. A model that is gone is a 409
 * `model_unavailable`. Silent: the card shows the refusal.
 */
export async function checkEmbedding(datasetId: string, embdId?: string): Promise<EmbeddingCheckView> {
  const dto = asRecord(
    await request<unknown>({ url: embeddingCheckPath(datasetId), method: "POST", data: { embd_id: embdId ?? null }, timeout: EMBEDDING_CHECK_TIMEOUT_MS }, { silent: true }),
  );
  return { ok: dto.ok === true, dimension: count(dto.dimension), expected: count(dto.expected) };
}
