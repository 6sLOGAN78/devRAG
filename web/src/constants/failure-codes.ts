/**
 * Failure codes and steps of a parse (common/ingest_codes.py) mapped to locale keys (UI-SPEC "Failure reasons").
 * Pure: returns keys, never text, so every language has its own wording and nothing unvetted reaches a row.
 */

const REASON_PREFIX = "datasets.details.reason";
const STEP_PREFIX = "datasets.details.step";

const REASON_LEAF: Readonly<Record<string, string>> = {
  no_readable_text: "noText",
  unsupported_type: "unsupported",
  chunker_unavailable: "chunker",
  file_damaged: "damaged",
  native_unavailable: "nativeUnavailable",
  file_too_large: "tooLarge",
  archive_limits_exceeded: "archive",
  provider_timeout: "providerTimeout",
  provider_rate_limited: "providerLimited",
  provider_unreachable: "providerUnreachable",
  provider_refused: "providerRefused",
  model_unavailable: "model",
  dimension_mismatch: "dimension",
  index_unavailable: "indexDown",
  storage_unavailable: "storage",
  worker_lost: "workerLost",
  too_many_chunks: "tooManyChunks",
  chunk_too_long: "chunkTooLong",
  qa_invalid: "qaInvalid",
  queue_unavailable: "queue",
  document_deleted: "documentGone",
  unexpected: "unknown",
};

/** The worker's step names; `parse` and `chunk` are the names the worker stores, `read` and `split` the UI-SPEC labels. */
const STEP_LEAF: Readonly<Record<string, string>> = {
  queue: "queue",
  fetch: "fetch",
  parse: "read",
  read: "read",
  chunk: "split",
  split: "split",
  embed: "embed",
  index: "index",
};

/** Codes for which trying again gives the same result (mirrors TERMINAL_CODES of the worker, R-158, R-155). */
const TERMINAL: ReadonlySet<string> = new Set([
  "no_readable_text",
  "unsupported_type",
  "chunker_unavailable",
  "file_too_large",
  "archive_limits_exceeded",
  "too_many_chunks",
  "chunk_too_long",
  "qa_invalid",
  "provider_refused",
  "dimension_mismatch",
  "model_unavailable",
  "document_deleted",
]);

/** Every failure code and step the SPA has fixed copy for. */
export const FAILURE_CODES: readonly string[] = Object.keys(REASON_LEAF);
export const STEPS: readonly string[] = Object.keys(STEP_LEAF);

const own = (table: Readonly<Record<string, string>>, name: string): string | undefined => (Object.hasOwn(table, name) ? table[name] : undefined);

export const MAX_FAILURE_MESSAGE_LENGTH = 300;

export function failureReasonKey(code: string): string {
  return `${REASON_PREFIX}.${own(REASON_LEAF, code) ?? "unknown"}`;
}

export function failureStepKey(step: string): string {
  return `${STEP_PREFIX}.${own(STEP_LEAF, step) ?? "unknown"}`;
}

export function isTerminalFailure(code: string): boolean {
  return TERMINAL.has(code);
}

export type FailureSentence = { key: string } | { text: string };

/**
 * The sentence for a stored failure. A known code gets fixed translated copy; an unknown code shows the server's plain
 * message when it has 1 to 300 characters, else the "unexpected" sentence. The text is shown as a text node.
 */
export function failureSentence(error: { code: string; message: string } | null | undefined): FailureSentence {
  if (error === null || error === undefined) return { key: failureReasonKey("unexpected") };
  if (own(REASON_LEAF, error.code) !== undefined) return { key: failureReasonKey(error.code) };
  const length = error.message.length;
  if (length >= 1 && length <= MAX_FAILURE_MESSAGE_LENGTH) return { text: error.message };
  return { key: failureReasonKey("unexpected") };
}

/** Whose chunking settings a dialog edits: one document's, or the dataset default. Kept here, out of the copy scan's reach. */
export const SETTINGS_MODES = { document: "document", dataset: "dataset" } as const;
export type SettingsMode = (typeof SETTINGS_MODES)[keyof typeof SETTINGS_MODES];
