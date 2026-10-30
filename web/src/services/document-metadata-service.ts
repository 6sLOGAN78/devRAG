import { datasetPath, datasetsPath } from "@/constants/api-paths";
import { request } from "./http";
import { asRecord, text } from "./mapping";

export type MetadataValue = string | number | boolean | null | string[];
export interface MetadataField { name: string; type: string; total: number; values: MetadataValue[] }
export interface MetadataPage { fields: MetadataField[]; page: number; hasMore: boolean }
export interface MetadataConfig { enabled: boolean; schema: { name: string; type: string; required: boolean }[]; modelId: string }

export async function editDocumentMetadata(datasetId: string, documentIds: string[], metadata: Record<string, MetadataValue>, mode: "merge" | "replace" = "merge"): Promise<void> {
  await request({url: `${datasetPath(datasetId)}/documents/metadatas`, method: "PATCH", data: {document_ids: documentIds, metadata, mode}, timeout: 65000}, {silent: true});
}

export async function listFlattenedMetadata(datasetIds: string[], signal?: AbortSignal, page = 1): Promise<MetadataPage> {
  const raw = asRecord(await request<unknown>({url: `${datasetsPath}/metadata/flattened`, method: "GET", params: {dataset_ids: datasetIds.join(","), page}, signal, timeout: 65000}, {silent: true}));
  const fields = Array.isArray(raw.fields) ? raw.fields.slice(0, 32).flatMap(item => {
    const field = asRecord(item);
    const name = text(field.name);
    const type = text(field.type);
    if (!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(name) || !["string", "number", "boolean", "null", "string_array", "mixed"].includes(type) || !Array.isArray(field.values)) return [];
    const values = field.values.slice(0, 100).filter(value => value === null || typeof value === "string" && value.length <= 4096 || typeof value === "number" && Number.isFinite(value) || typeof value === "boolean" || Array.isArray(value) && value.length <= 32 && value.every(part => typeof part === "string" && part.length <= 4096));
    return [{name, type, total: typeof field.total === "number" && Number.isInteger(field.total) && field.total >= values.length ? field.total : values.length, values}];
  }) : [];
  return {fields,page: typeof raw.page === "number" && Number.isInteger(raw.page) ? raw.page : page,hasMore:raw.has_more === true};
}

export async function getMetadataConfig(datasetId: string, signal?: AbortSignal): Promise<MetadataConfig> {
  const raw = asRecord(await request<unknown>({url: `${datasetPath(datasetId)}/metadata/config`, method: "GET", signal, timeout: 65000}, {silent: true}));
  return {
    enabled: raw.enabled === true,
    modelId: text(raw.model_id).slice(0, 128),
    schema: Array.isArray(raw.schema) ? raw.schema.slice(0, 32).flatMap(item => {
      const field = asRecord(item);
      const name = text(field.name);
      const type = text(field.type);
      return /^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(name) && ["string", "number", "boolean", "string_array"].includes(type) ? [{name, type, required: field.required === true}] : [];
    }) : [],
  };
}
