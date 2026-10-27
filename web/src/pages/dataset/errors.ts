import type { SettingsMode } from "@/constants/failure-codes";
import { ApiError } from "@/services/http";

/**
 * Which page-level state a failed dataset detail request maps to (D-27, T-03-31-01). A 404 is "Dataset not found":
 * the server answers it for a dataset that is missing, deleted, private to someone else or in a workspace the caller
 * has not joined, and the page shows one identical block for all of them. Anything else (a 5xx, a dropped connection)
 * is a failure the user can retry and says nothing about whether the dataset exists.
 */
export type DatasetPageState = "notFound" | "error";

export function datasetPageState(error: unknown): DatasetPageState {
  return error instanceof ApiError && error.status === 404 ? "notFound" : "error";
}

export { confirmCountsOf } from "@/services/document-service";

/** HTTP statuses that mean "no answer in time" from the server side. */
const GATEWAY_TIMEOUT = 504;
const REQUEST_TIMEOUT = 408;
const MAX_DETAIL_LENGTH = 300;

/**
 * True for a request that ran out of time: the client's own timeout (`kind`) or a timeout status. Never decided from
 * message text, which is translated (FE-06).
 */
export function isTimeout(error: unknown): boolean {
  return error instanceof ApiError && (error.kind === "timeout" || error.status === GATEWAY_TIMEOUT || error.status === REQUEST_TIMEOUT);
}

/** The refusal reason the API puts in `data.reason`, or "" when there is none. */
function reasonOf(error: unknown): string {
  if (!(error instanceof ApiError)) return "";
  const data = error.data;
  if (typeof data !== "object" || data === null) return "";
  const reason = (data as Record<string, unknown>).reason;
  return typeof reason === "string" ? reason : "";
}

const statusOf = (error: unknown): number => (error instanceof ApiError ? error.status : -1);

/** Where a failure goes: a toast or alert with locale key `key` (null: say nothing), and whether to refetch. */
export interface Placed {
  key: string | null;
  /** Refetch the list or the page now. */
  refetch?: boolean;
  /** Refetch when the user dismisses the message. */
  refetchOnDismiss?: boolean;
  /** Bounded server text shown as a text node under the message. */
  detail?: string;
  /** Always false: a provider refusal or any failure placed here is never a session event. */
  sessionEvent?: false;
}

const FORBIDDEN: Placed = { key: "workspace.forbidden", refetch: true };
const GONE: Placed = { key: "datasets.files.gone", refetch: true };

/** Answers shared by the row actions. Returns null when the answer is not one of them. */
function rowActionCommon(error: unknown): Placed | null {
  const status = statusOf(error);
  if (status === 403) return FORBIDDEN;
  if (status === 404) return GONE;
  return null;
}

/** Start parsing (row actions table of the UI-SPEC). */
export function parseFailureOf(error: unknown): Placed {
  const status = statusOf(error);
  const reason = reasonOf(error);
  if (status === 400 && reason === "parse_unavailable") return { key: "datasets.parse.error.unavailable" };
  if (status === 400 && reason === "chunker_unavailable") return { key: "datasets.parse.error.chunker" };
  if (status === 409 && reason === "already_running") return { key: null, refetch: true };
  if (status === 409 && reason === "model_unavailable") return { key: "datasets.parse.error.model" };
  if (status === 503 && reason === "queue_unavailable") return { key: "datasets.parse.error.queue" };
  if (status === 503 && reason === "index_unavailable") return { key: "datasets.parse.error.index" };
  if (status === 429) return { key: "datasets.parse.error.limited" };
  return rowActionCommon(error) ?? { key: "datasets.parse.error.startFallback" };
}

/** Cancel parsing. */
export function cancelFailureOf(error: unknown): Placed {
  return rowActionCommon(error) ?? { key: "datasets.parse.error.cancelFallback" };
}

/** The "In search" switch of a document. */
export function switchFailureOf(error: unknown): Placed {
  if (statusOf(error) === 503 && reasonOf(error) === "index_unavailable") return { key: "datasets.parse.error.index" };
  return rowActionCommon(error) ?? { key: "datasets.parse.error.switchFallback" };
}

/** Saving chunking settings for one document or for the dataset default (own wording for 404, Checker Flag 4). */
export function settingsFailureOf(error: unknown, mode: SettingsMode): Placed {
  const status = statusOf(error);
  const reason = reasonOf(error);
  if (status === 400 && (reason === "chunker_unavailable" || reason === "parser_unavailable")) return { key: "datasets.chunking.error.method" };
  if (status === 409 && reason === "parse_running") return { key: "datasets.chunking.error.running", refetch: true };
  if (status === 404) return mode === "dataset" ? { key: "datasets.chunking.error.datasetGone", refetch: true } : GONE;
  if (status === 403) return FORBIDDEN;
  return { key: "datasets.chunking.error.fallback" };
}

/** The form field a `parser_config_invalid` answer names in `data.field`, or null when it names none that the form has. */
export function invalidFieldOf(error: unknown): "chunkSize" | "delimiters" | "overlap" | "pageRanges" | "layoutRecognize" | null {
  if (!(error instanceof ApiError) || error.status !== 400 || reasonOf(error) !== "parser_config_invalid") return null;
  const data = error.data;
  const field = typeof data === "object" && data !== null ? (data as Record<string, unknown>).field : undefined;
  if (field === "chunk_token_num") return "chunkSize";
  if (field === "delimiter") return "delimiters";
  if (field === "overlapped_percent") return "overlap";
  if (field === "layout_recognize") return "layoutRecognize";
  if (field === "pages") return "pageRanges";
  return null;
}

/** Locale key of the stored-method warning, per mode (Checker Flag 4). */
export function storedUnavailableKey(mode: SettingsMode): string {
  return mode === "dataset" ? "datasets.chunking.storedUnavailableDataset" : "datasets.chunking.storedUnavailable";
}

const boundedDetail = (error: unknown): string | undefined => {
  if (!(error instanceof ApiError)) return undefined;
  const data = error.data;
  const fromData = typeof data === "object" && data !== null ? (data as Record<string, unknown>).detail : undefined;
  const text = typeof fromData === "string" ? fromData.trim() : "";
  return text.length > 0 ? text.slice(0, MAX_DETAIL_LENGTH) : undefined;
};

/**
 * The chunk editor's table: an edit, an add, or the chunk switch. Returns locale keys, never text. A provider's own
 * reason (at most 300 characters) rides along as `detail`. A provider refusal is a 400, never a session event.
 */
export function chunkFailureOf(error: unknown, kind: "edit" | "add" | "switch"): Placed {
  const status = statusOf(error);
  const reason = reasonOf(error);
  const fallback = kind === "switch" ? "inspector.switch.failed" : "inspector.editor.refused.fallback";
  const placed = (key: string, more: Partial<Placed> = {}): Placed => ({ key, sessionEvent: false, ...more });

  if (status === 403) return placed("workspace.forbidden");
  if (status === 404) {
    if (kind === "add") return placed("inspector.editor.refused.documentGone", { refetchOnDismiss: true });
    return placed("inspector.editor.refused.gone", { refetchOnDismiss: true });
  }
  if (status === 409 && reason === "parse_running") return placed("inspector.editor.refused.running", { refetch: true });
  if (status === 503 && reason === "index_unavailable") return placed("inspector.editor.refused.index");
  if (kind === "switch") return placed(fallback);

  if (isTimeout(error) || reason === "provider_timeout") return placed("inspector.editor.refused.timeout");
  if (status === 429 || reason === "provider_rate_limited") return placed("inspector.editor.refused.limited");
  if (status === 400 && reason === "provider_refused") return placed("inspector.editor.refused.provider", { detail: boundedDetail(error) });
  if (reason === "provider_unreachable") return placed("inspector.editor.refused.unreachable");
  if (reason === "dimension_mismatch") return placed("inspector.editor.refused.dimension");
  if (status === 409 && reason === "model_unavailable") return placed("inspector.editor.refused.model");
  if (status === 400 && reason === "chunk_too_long") return placed("inspector.editor.refused.tooLong");
  return placed(fallback);
}
