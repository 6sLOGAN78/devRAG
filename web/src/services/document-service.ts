import { datasetDocumentPath, datasetDocumentsPath, datasetParsePath, datasetStatusPath, documentUploadPath } from "@/constants/api-paths";
import { ApiError, expectRecord, request } from "./http";
import { asRecord, clampWhole, count, pageRangesOf, text } from "./mapping";

/**
 * Document APIs (plans 03-16 and 03-17). Every mapper copies an explicit field list, so an unexpected field from the
 * server (a storage location, say) never reaches component state. File names are user text: render them as text nodes.
 */

/** One document as the dataset page and the upload dialog show it. */
export interface DocumentView {
  id: string;
  name: string;
  size: number;
  /** `pdf`, `doc`, `visual`, `aural` or `other`. */
  type: string;
  suffix: string;
  /** Parse state; `"0"` (not started) for every Phase 3 document. */
  run: string;
  progress: number;
  datasetId: string;
  createdBy: string;
  parserId: string;
  chunkNum: number;
  updateTime: number;
  createTime: number;
  /** Same number as `chunkNum`, under the name of the Phase 4 API. */
  chunkCount: number;
  tokenNum: number;
  parseable: boolean;
  /** The document's own search switch. */
  enabled: boolean;
  /** A vetted `data:image/jpeg` or `data:image/png` URL, or null. */
  thumbnail: string | null;
  lastLogId: string | null;
  pagesTotal: number | null;
  pagesWithoutText: number | null;
  /** Server text, cut to 300 characters; render as a text node. */
  progressMessage: string;
  error: DocumentErrorView | null;
}

export interface DocumentErrorView {
  step: string;
  code: string;
  message: string;
}

export interface DocumentPage {
  items: DocumentView[];
  total: number;
}

export interface ListDocumentsInput {
  datasetId: string;
  page: number;
  pageSize: number;
  keywords: string;
}

export interface UploadOptions {
  signal?: AbortSignal;
  /** Bytes sent so far and the request's total; the total can be missing. */
  onProgress?: (loaded: number, total: number | undefined) => void;
}

/** Bounds the API enforces; the service applies them first so a bad value never becomes a request. */
export const MAX_DOCUMENT_PAGE_SIZE = 100;
export const MAX_DOCUMENT_KEYWORDS_LENGTH = 128;

export const MAX_PROGRESS_MESSAGE_LENGTH = 300;
const THUMBNAIL_PREFIXES = ["data:image/jpeg;base64,", "data:image/png;base64,"];

const optionalCount = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);

/** A thumbnail is kept only when it is a base64 JPEG or PNG data URL; anything else (a link, a script) becomes null. */
function vetThumbnail(value: unknown): string | null {
  return typeof value === "string" && THUMBNAIL_PREFIXES.some((prefix) => value.startsWith(prefix)) ? value : null;
}

function toError(raw: unknown): DocumentErrorView | null {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const dto = raw as Record<string, unknown>;
  // One character past the limit is kept, so a message that is too long stays detectable and is never shown cut (D-08).
  return { step: text(dto.step), code: text(dto.code), message: text(dto.message).slice(0, MAX_PROGRESS_MESSAGE_LENGTH + 1) };
}

export function toDocument(raw: unknown): DocumentView {
  const dto = asRecord(raw);
  const chunks = count(dto.chunk_count !== undefined ? dto.chunk_count : dto.chunk_num);
  return {
    id: text(dto.id),
    name: text(dto.name),
    size: count(dto.size),
    type: text(dto.type),
    suffix: text(dto.suffix),
    run: text(dto.run),
    progress: count(dto.progress),
    datasetId: text(dto.dataset_id),
    createdBy: text(dto.created_by),
    parserId: text(dto.parser_id),
    chunkNum: chunks,
    updateTime: count(dto.update_time),
    createTime: count(dto.create_time),
    chunkCount: chunks,
    tokenNum: count(dto.token_num),
    parseable: dto.parseable !== false,
    enabled: dto.enabled !== false,
    thumbnail: vetThumbnail(dto.thumbnail),
    lastLogId: typeof dto.last_log_id === "string" && dto.last_log_id !== "" ? dto.last_log_id : null,
    pagesTotal: optionalCount(dto.pages_total),
    pagesWithoutText: optionalCount(dto.pages_without_text),
    progressMessage: text(dto.progress_message).slice(0, MAX_PROGRESS_MESSAGE_LENGTH),
    error: toError(dto.error),
  };
}

/**
 * POST /api/v1/documents/upload: one file per request (per-file progress, bounded server memory). `timeout: 0` because a
 * 100 MB file on a slow link takes minutes and the SPA's 10 s default would cut it (Pitfall 8); the request is ended only
 * through the signal. No content-type header is set, so the browser writes the multipart boundary. Silent: the dialog shows each
 * file's answer on its own row. Resolves to the stored document, whose `name` may differ from the file's (D-14).
 */
export async function uploadDocument(datasetId: string, file: File, options: UploadOptions = {}): Promise<DocumentView> {
  const form = new FormData();
  form.append("file", file, file.name);
  const data = await request<unknown>(
    {
      url: documentUploadPath,
      method: "POST",
      params: { dataset_id: datasetId },
      data: form,
      timeout: 0,
      signal: options.signal,
      onUploadProgress: (event) => options.onProgress?.(event.loaded, event.total),
    },
    { silent: true },
  );
  const first = Array.isArray(data) ? data[0] : undefined;
  return toDocument(expectRecord<Record<string, unknown>>(first, "the document upload", ["id"]));
}

/** GET /api/v1/datasets/{id}/documents: one page, newest first. Silent: the page renders its own error state. */
export async function listDocuments(input: ListDocumentsInput): Promise<DocumentPage> {
  const params: Record<string, string | number> = {
    page: clampWhole(input.page, 1, Number.MAX_SAFE_INTEGER),
    page_size: clampWhole(input.pageSize, 1, MAX_DOCUMENT_PAGE_SIZE),
  };
  const keywords = input.keywords.slice(0, MAX_DOCUMENT_KEYWORDS_LENGTH);
  if (keywords !== "") params.keywords = keywords;
  const data = asRecord(await request<unknown>({ url: datasetDocumentsPath(input.datasetId), method: "GET", params }, { silent: true }));
  return { items: Array.isArray(data.items) ? data.items.map(toDocument) : [], total: count(data.total) };
}

/**
 * DELETE /api/v1/datasets/{id}/documents: all or nothing (one document the caller may not remove refuses the batch).
 * Silent: the confirmation shows the refusal. Resolves to how many documents were removed.
 */
export async function deleteDocuments(datasetId: string, ids: string[]): Promise<number> {
  const data = asRecord(await request<unknown>({ url: datasetDocumentsPath(datasetId), method: "DELETE", data: { ids } }, { silent: true }));
  return count(data.deleted);
}


/** Parse requests wait on page counting and task creation, so they get 30 s (UI-SPEC HTTP client rules). */
export const PARSE_TIMEOUT_MS = 30000;
export const SWITCH_TIMEOUT_MS = 30000;
const MAX_SETTINGS_TIMEOUT_MS = 30000;

export interface ParseResult {
  /** Ids whose parsing was started. */
  started: string[];
  /** Ids whose running parse was cancelled. */
  cancelled: string[];
}

/** One document that a replacing re-parse would overwrite, as the 409 `confirm_required` answer lists it. */
export interface ConfirmCount {
  id: string;
  name: string;
  chunkCount: number;
  editedCount: number;
  manualCount: number;
}

/**
 * Reads the documents a 409 `confirm_required` answer names. Anything that is not that answer yields an empty list.
 * The answer's `data.documents` is mapped by an explicit field list.
 */
export function confirmCountsOf(error: unknown): ConfirmCount[] {
  if (!(error instanceof ApiError) || error.status !== 409) return [];
  const documents = asRecord(error.data).documents;
  if (!Array.isArray(documents)) return [];
  return documents.map((raw) => {
    const dto = asRecord(raw);
    return { id: text(dto.id), name: text(dto.name), chunkCount: count(dto.chunk_count), editedCount: count(dto.edited_count), manualCount: count(dto.manual_count) };
  });
}

const idsOf = (value: unknown): string[] =>
  Array.isArray(value) ? value.map((item) => (typeof item === "string" ? item : asRecord(item).id)).filter((id): id is string => typeof id === "string" && id !== "") : [];

/**
 * POST /api/v1/datasets/{id}/documents/parse: `run` "1" starts, "2" cancels. A re-parse that would replace chunks is
 * refused with a 409 `confirm_required` until `confirmReplace` is true. Silent: the table shows the refusal.
 */
export async function parseDocuments(datasetId: string, ids: string[], run: "1" | "2", confirmReplace = false): Promise<ParseResult> {
  const data: Record<string, unknown> = { doc_ids: ids, run };
  if (confirmReplace) data.confirm_replace = true;
  const body = asRecord(await request<unknown>({ url: datasetParsePath(datasetId), method: "POST", data, timeout: PARSE_TIMEOUT_MS }, { silent: true }));
  return { started: idsOf(body.started), cancelled: idsOf(body.cancelled) };
}

/** POST .../documents/batch-update-status with `doc_ids` (the route also accepts `doc_id`, R-162). Resolves to the updated ids. */
export async function setDocumentsEnabled(datasetId: string, ids: string[], enabled: boolean): Promise<{ updated: string[]; enabled: boolean }> {
  const body = asRecord(
    await request<unknown>({ url: datasetStatusPath(datasetId), method: "POST", data: { doc_ids: ids, status: enabled ? "1" : "0" }, timeout: SWITCH_TIMEOUT_MS }, { silent: true }),
  );
  return { updated: idsOf(body.updated), enabled: body.enabled === true };
}

/** One document opened on its own: the list row plus its chunking values and the kind of preview it supports. */
export interface DocumentAssetView { id: string; kind: "image" | "table"; caption: string; page: number | null; width: number; height: number }

function assetsOf(raw: unknown): DocumentAssetView[] {
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  return raw.slice(0, 128).flatMap((value) => {
    const a = asRecord(value), id = text(a.id);
    if (!/^[a-f0-9]{32}$/.test(id) || seen.has(id) || (a.kind !== "image" && a.kind !== "table") || count(a.width) < 1 || count(a.height) < 1) return [];
    seen.add(id);
    return [{ id, kind: a.kind, caption: text(a.caption).slice(0, 1024), page: optionalCount(a.page), width: count(a.width), height: count(a.height) }];
  });
}

export interface DocumentDetailView extends DocumentView {
  assets?: DocumentAssetView[];
  pages?: [number, number][];
  layoutRecognize?: boolean | string;
  chunkTokenNum: number;
  delimiter: string;
  overlappedPercent: number;
  /** `pages` (a PDF with page images) or `none`; any other server value becomes `none`. */
  preview: "pages" | "none";
  pagesTotal: number | null;
}

/** GET /api/v1/datasets/{id}/documents/{doc}. Silent: the page renders its own error state. */
export async function getDocument(datasetId: string, docId: string): Promise<DocumentDetailView> {
  const raw = await request<unknown>({ url: datasetDocumentPath(datasetId, docId), method: "GET" }, { silent: true });
  const dto = asRecord(expectRecord<Record<string, unknown>>(raw, "the document", ["id"]));
  return {
    ...toDocument(dto),
    assets: assetsOf(dto.assets),
    chunkTokenNum: count(dto.chunk_token_num),
    delimiter: text(dto.delimiter),
    overlappedPercent: count(dto.overlapped_percent),
    preview: dto.preview === "pages" ? "pages" : "none",
    ...(typeof dto.layout_recognize === "boolean" || typeof dto.layout_recognize === "string" ? { layoutRecognize: dto.layout_recognize } : {}),
    ...(dto.pages !== undefined ? { pages: pageRangesOf(dto.pages) } : {}),
  };
}

export interface DocumentSettingsChanges {
  pages?: [number, number][];
  layoutRecognize?: boolean | string;
  parserId?: string;
  chunkTokenNum?: number;
  delimiter?: string;
  overlappedPercent?: number;
}

/**
 * PATCH .../documents/{doc}: only the keys given are sent, so an unchanged value is never resent. The call changes
 * the document's method and chunking values without re-chunking. Silent: the dialog shows the refusal.
 */
export async function updateDocumentSettings(datasetId: string, docId: string, changes: DocumentSettingsChanges): Promise<DocumentDetailView> {
  const data: Record<string, unknown> = {};
  if (changes.parserId !== undefined) data.parser_id = changes.parserId;
  const config: Record<string, unknown> = {};
  if (changes.chunkTokenNum !== undefined) config.chunk_token_num = changes.chunkTokenNum;
  if (changes.delimiter !== undefined) config.delimiter = changes.delimiter;
  if (changes.overlappedPercent !== undefined) config.overlapped_percent = changes.overlappedPercent;
  if (changes.layoutRecognize !== undefined) config.layout_recognize = changes.layoutRecognize;
  if (changes.pages !== undefined) config.pages = changes.pages;
  if (Object.keys(config).length > 0) data.parser_config = config;
  const raw = await request<unknown>({ url: datasetDocumentPath(datasetId, docId), method: "PATCH", data, timeout: MAX_SETTINGS_TIMEOUT_MS }, { silent: true });
  const dto = asRecord(expectRecord<Record<string, unknown>>(raw, "the document settings", ["id"]));
  return {
    ...toDocument(dto),
    assets: assetsOf(dto.assets),
    chunkTokenNum: count(dto.chunk_token_num),
    delimiter: text(dto.delimiter),
    overlappedPercent: count(dto.overlapped_percent),
    preview: dto.preview === "pages" ? "pages" : "none",
    ...(typeof dto.layout_recognize === "boolean" || typeof dto.layout_recognize === "string" ? { layoutRecognize: dto.layout_recognize } : {}),
    ...(dto.pages !== undefined ? { pages: pageRangesOf(dto.pages) } : {}),
  };
}
