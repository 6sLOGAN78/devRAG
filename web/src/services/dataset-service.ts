import { datasetPath, datasetsPath } from "@/constants/api-paths";
import { request } from "./http";
import { asRecord, clampWhole, count, pageRangesOf, text } from "./mapping";

/**
 * Dataset APIs (plans 03-14 and 03-18). Every mapper copies an explicit field list and coerces what it reads, so an
 * unexpected field or type from the server never reaches component state. Names and descriptions are user text and
 * must be rendered as text nodes only.
 */

/** One dataset as the gallery shows it. */
export interface DatasetView {
  id: string;
  name: string;
  description: string;
  /** `me` (only the creator) or `team` (the workspace). */
  permission: string;
  /** Composite id of the embedding model the dataset was created with. */
  embdId: string;
  /** Dimension of that model, or null before one is known. */
  embeddingDimension: number | null;
  docNum: number;
  createdBy: string;
  tenantId: string;
  updateTime: number;
  pagerank?: number;
}

/** What one upload request may carry, from the server's settings (KB-04). */
export interface UploadLimitsView {
  maxFileBytes: number;
  maxFilesPerRequest: number;
  maxDocuments: number;
  allowedExtensions: string[];
}

/** The dataset's default chunking values (the document dialog and the default chunking dialog load them). */
export interface DatasetParserConfig {
  pages?: [number, number][];
  layoutRecognize?: boolean | string;
  resumeModel?: string;
  resumeUseModel?: boolean;
  asrModel?: string;
  audioLanguage?: string;
  imageModel?: string;
  pictureOcrOnly?: boolean;
  chunkTokenNum: number;
  delimiter: string;
  overlappedPercent: number;
}

export const DEFAULT_CHUNK_TOKEN_NUM = 512;
export const DEFAULT_DELIMITER = "\n!?;。；！？";
export const DEFAULT_OVERLAPPED_PERCENT = 0;

/** One dataset opened on its own page. */
export interface DatasetDetailView extends DatasetView {
  language: string;
  parserId: string;
  parserConfig: DatasetParserConfig;
  chunkNum: number;
  tokenNum: number;
  createTime: number;
  /** Null when the server sent none; the upload dialog then falls back to the server's refusals. */
  uploadLimits: UploadLimitsView | null;
}

export interface DatasetPage {
  items: DatasetView[];
  total: number;
}

export interface ListDatasetsInput {
  tenantId: string;
  page: number;
  pageSize: number;
  keywords: string;
}

export interface CreateDatasetInput {
  tenantId: string;
  name: string;
  description?: string;
  embdId?: string;
  permission?: string;
}

/** The fields a settings save may change (plan 03-18). An absent key is no change; a null description clears it. */
export interface DatasetChanges {
  pagerank?: number;
  name?: string;
  description?: string | null;
  permission?: string;
  embdId?: string;
}

/** Bounds the API enforces; the service applies them first so a bad value never becomes a request. */
export const MAX_PAGE_SIZE = 100;
export const MAX_KEYWORDS_LENGTH = 128;
/** The create call may wait on index provisioning (D-26). */
export const CREATE_TIMEOUT_MS = 30000;

function toDataset(raw: unknown): DatasetView {
  const dto = asRecord(raw);
  return {
    id: text(dto.id),
    name: text(dto.name),
    description: text(dto.description),
    permission: text(dto.permission),
    embdId: text(dto.embd_id),
    embeddingDimension: typeof dto.embedding_dimension === "number" && Number.isFinite(dto.embedding_dimension) ? dto.embedding_dimension : null,
    docNum: count(dto.doc_num),
    createdBy: text(dto.created_by),
    tenantId: text(dto.tenant_id),
    updateTime: count(dto.update_time),
    ...(dto.pagerank!==undefined ? {pagerank:count(dto.pagerank)} : {}),
  };
}

function toLimits(raw: unknown): UploadLimitsView | null {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const dto = raw as Record<string, unknown>;
  return {
    maxFileBytes: count(dto.max_file_bytes),
    maxFilesPerRequest: count(dto.max_files_per_request),
    maxDocuments: count(dto.max_documents),
    allowedExtensions: Array.isArray(dto.allowed_extensions) ? dto.allowed_extensions.filter((ext): ext is string => typeof ext === "string") : [],
  };
}

function toParserConfig(raw: unknown): DatasetParserConfig {
  const dto = asRecord(raw);
  const tokens = count(dto.chunk_token_num);
  const overlap = count(dto.overlapped_percent);
  return {
    chunkTokenNum: tokens > 0 ? tokens : DEFAULT_CHUNK_TOKEN_NUM,
    delimiter: typeof dto.delimiter === "string" && dto.delimiter !== "" ? dto.delimiter : DEFAULT_DELIMITER,
    overlappedPercent: overlap > 0 ? overlap : DEFAULT_OVERLAPPED_PERCENT,
    ...(dto.resume_model !== undefined ? {resumeModel:text(dto.resume_model)} : {}),
    ...(dto.resume_use_model !== undefined ? {resumeUseModel:dto.resume_use_model===true} : {}),
    ...(dto.asr_model !== undefined ? {asrModel:text(dto.asr_model)} : {}),
    ...(dto.audio_language !== undefined ? {audioLanguage:text(dto.audio_language)} : {}),
    ...(dto.image_model !== undefined ? {imageModel:text(dto.image_model)} : {}),
    ...(dto.picture_ocr_only !== undefined ? {pictureOcrOnly:dto.picture_ocr_only===true} : {}),
    ...(typeof dto.layout_recognize === "boolean" || typeof dto.layout_recognize === "string" ? { layoutRecognize: dto.layout_recognize } : {}),
    ...(dto.pages !== undefined ? { pages: pageRangesOf(dto.pages) } : {}),
  };
}

function toDetail(raw: unknown): DatasetDetailView {
  const dto = asRecord(raw);
  return {
    ...toDataset(raw),
    language: text(dto.language),
    parserId: text(dto.parser_id),
    parserConfig: toParserConfig(dto.parser_config),
    chunkNum: count(dto.chunk_num),
    tokenNum: count(dto.token_num),
    createTime: count(dto.create_time),
    uploadLimits: toLimits(dto.upload_limits),
  };
}

/** GET /api/v1/datasets: one page of the workspace's datasets. Silent: the gallery renders its own error state. */
export async function listDatasets(input: ListDatasetsInput): Promise<DatasetPage> {
  const params: Record<string, string | number> = {
    tenant_id: input.tenantId,
    page: clampWhole(input.page, 1, Number.MAX_SAFE_INTEGER),
    page_size: clampWhole(input.pageSize, 1, MAX_PAGE_SIZE),
  };
  const keywords = input.keywords.slice(0, MAX_KEYWORDS_LENGTH);
  if (keywords !== "") params.keywords = keywords;
  const data = asRecord(await request<unknown>({ url: datasetsPath, method: "GET", params }, { silent: true }));
  return { items: Array.isArray(data.items) ? data.items.map(toDataset) : [], total: count(data.total) };
}

/** GET /api/v1/datasets/{id}: the dataset with the limits its uploads must respect. */
export async function getDataset(id: string): Promise<DatasetDetailView> {
  return toDetail(await request<unknown>({ url: datasetPath(id), method: "GET" }, { silent: true }));
}

/**
 * POST /api/v1/datasets. Silent: the dialog shows the refusal (a duplicate name, a locked or unsupported model) inline.
 * Fields the caller did not choose are left out so the server applies its defaults (the workspace's default embedding model).
 */
export async function createDataset(input: CreateDatasetInput): Promise<DatasetView> {
  const data: Record<string, string> = { tenant_id: input.tenantId, name: input.name };
  if (input.description !== undefined) data.description = input.description;
  if (input.embdId !== undefined) data.embd_id = input.embdId;
  if (input.permission !== undefined) data.permission = input.permission;
  return toDataset(await request<unknown>({ url: datasetsPath, method: "POST", data, timeout: CREATE_TIMEOUT_MS }, { silent: true }));
}

/**
 * PUT /api/v1/datasets/{id}: only the changed fields, in snake_case. An undefined field is left out, so an unchanged
 * value is never resent, and no workspace selector is sent (the server takes the workspace from the dataset). Silent:
 * the dialog shows the refusal inline.
 */
export async function updateDataset(id: string, changes: DatasetChanges): Promise<DatasetView> {
  const data: Record<string, string | number | null> = {};
  if (changes.pagerank !== undefined) data.pagerank=changes.pagerank;
  if (changes.name !== undefined) data.name = changes.name;
  if (changes.description !== undefined) data.description = changes.description;
  if (changes.permission !== undefined) data.permission = changes.permission;
  if (changes.embdId !== undefined) data.embd_id = changes.embdId;
  return toDataset(await request<unknown>({ url: datasetPath(id), method: "PUT", data, timeout: CREATE_TIMEOUT_MS }, { silent: true }));
}

/**
 * DELETE /api/v1/datasets with `{ids, tenant_id}`. Authorisation is all or nothing, so callers delete one dataset per
 * request. Silent: the confirmation shows the refusal. Resolves to the ids the server removed.
 */
export async function deleteDatasets(ids: string[], tenantId: string): Promise<string[]> {
  const data = asRecord(await request<unknown>({ url: datasetsPath, method: "DELETE", data: { ids, tenant_id: tenantId }, timeout: CREATE_TIMEOUT_MS }, { silent: true }));
  return Array.isArray(data.deleted) ? data.deleted.filter((id): id is string => typeof id === "string") : [];
}

/** The default chunking method and values a save may change. An absent key is no change (the server merges). */
export type DatasetChunkingInput = Partial<{
  pages: [number, number][];
  layoutRecognize: boolean | string;
  resumeModel?: string;
  resumeUseModel?: boolean;
  asrModel?: string;
  audioLanguage?: string;
  imageModel: string;
  pictureOcrOnly: boolean;
  parserId: string;
  chunkTokenNum: number;
  delimiter: string;
  overlappedPercent: number;
}>;

/**
 * PUT /api/v1/datasets/{id} with the default chunking method and values: only the keys given are sent, and the server
 * merges a partial `parser_config` with what is stored. Existing documents keep their own values. Silent: the dialog
 * shows the refusal inline.
 */
export async function updateDatasetChunking(id: string, input: DatasetChunkingInput): Promise<DatasetDetailView> {
  const data: Record<string, unknown> = {};
  if (input.parserId !== undefined) data.parser_id = input.parserId;
  const config: Record<string, unknown> = {};
  if (input.chunkTokenNum !== undefined) config.chunk_token_num = input.chunkTokenNum;
  if (input.delimiter !== undefined) config.delimiter = input.delimiter;
  if (input.overlappedPercent !== undefined) config.overlapped_percent = input.overlappedPercent;
  if (input.resumeModel !== undefined) config.resume_model = input.resumeModel;
  if (input.resumeUseModel !== undefined) config.resume_use_model = input.resumeUseModel;
  if (input.asrModel !== undefined) config.asr_model = input.asrModel;
  if (input.audioLanguage !== undefined) config.audio_language = input.audioLanguage || null;
  if (input.imageModel !== undefined) config.image_model = input.imageModel;
  if (input.pictureOcrOnly !== undefined) config.picture_ocr_only = input.pictureOcrOnly;
  if (input.layoutRecognize !== undefined) config.layout_recognize = input.layoutRecognize;
  if (input.pages !== undefined) config.pages = input.pages;
  if (Object.keys(config).length > 0) data.parser_config = config;
  return toDetail(await request<unknown>({ url: datasetPath(id), method: "PUT", data, timeout: CREATE_TIMEOUT_MS }, { silent: true }));
}
