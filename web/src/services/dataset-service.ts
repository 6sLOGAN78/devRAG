import { datasetPath, datasetsPath } from "@/constants/api-paths";
import { request } from "./http";

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
}

/** What one upload request may carry, from the server's settings (KB-04). */
export interface UploadLimitsView {
  maxFileBytes: number;
  maxFilesPerRequest: number;
  maxDocuments: number;
  allowedExtensions: string[];
}

/** One dataset opened on its own page. */
export interface DatasetDetailView extends DatasetView {
  language: string;
  parserId: string;
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

/** Bounds the API enforces; the service applies them first so a bad value never becomes a request. */
export const MAX_PAGE_SIZE = 100;
export const MAX_KEYWORDS_LENGTH = 128;
/** The create call may wait on index provisioning (D-26). */
export const CREATE_TIMEOUT_MS = 30000;

const text = (value: unknown): string => {
  if (typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "";
};
const count = (value: unknown): number => {
  const n = typeof value === "string" && value.trim() !== "" ? Number(value) : value;
  return typeof n === "number" && Number.isFinite(n) ? n : 0;
};
const asRecord = (value: unknown): Record<string, unknown> => (typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {});

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

function toDetail(raw: unknown): DatasetDetailView {
  const dto = asRecord(raw);
  return {
    ...toDataset(raw),
    language: text(dto.language),
    parserId: text(dto.parser_id),
    chunkNum: count(dto.chunk_num),
    tokenNum: count(dto.token_num),
    createTime: count(dto.create_time),
    uploadLimits: toLimits(dto.upload_limits),
  };
}

function clampWhole(value: number, low: number, high: number): number {
  if (!Number.isFinite(value)) return low;
  return Math.min(high, Math.max(low, Math.floor(value)));
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
