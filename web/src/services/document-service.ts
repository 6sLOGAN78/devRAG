import { datasetDocumentsPath, documentUploadPath } from "@/constants/api-paths";
import { expectRecord, request } from "./http";
import { asRecord, clampWhole, count, text } from "./mapping";

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

function toDocument(raw: unknown): DocumentView {
  const dto = asRecord(raw);
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
    chunkNum: count(dto.chunk_num),
    updateTime: count(dto.update_time),
    createTime: count(dto.create_time),
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

