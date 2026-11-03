import { datasetPath } from "@/constants/api-paths";
import { http, request } from "./http";
import { asRecord, count, text } from "./mapping";

export interface Alteration {
  actor: string;
  type: "raptor";
  generation: string;
  outcome: "done" | "failed";
  time: number;
  deletedCount: number;
}

export interface AlterationPage {
  items: Alteration[];
  total: number;
  page: number;
  size: number;
}

export async function listAlterations(datasetId: string, page = 1, signal?: AbortSignal): Promise<AlterationPage> {
  const raw = asRecord(await request<unknown>({ url: `${datasetPath(datasetId)}/artifacts/alteration`, method: "GET",
    params: { page, size: 20 }, signal }, { silent: true }));
  const items = Array.isArray(raw.items) ? raw.items.slice(0, 20).flatMap(item => {
    const row = asRecord(item);
    if (row.type !== "raptor" || !["done", "failed"].includes(text(row.outcome))) return [];
    return [{ actor: text(row.actor), type: "raptor" as const, generation: text(row.generation),
      outcome: row.outcome as "done" | "failed", time: count(row.time), deletedCount: count(row.deleted_count) }];
  }) : [];
  return { items, total: count(raw.total), page: count(raw.page), size: count(raw.size) };
}

export async function deleteRaptorResults(datasetId: string): Promise<{ deletedCount: number; artifactCount: number }> {
  const raw = asRecord(await request<unknown>({ url: `${datasetPath(datasetId)}/raptor`, method: "DELETE" }, { silent: true }));
  if (raw.type !== "raptor") throw new Error("Invalid derived deletion response");
  return { deletedCount: count(raw.deleted_count), artifactCount: count(raw.artifact_count) };
}

export async function downloadRaptorArtifact(filename: string): Promise<Blob> {
  if (!/^[0-9a-f]{32}\.json$/.test(filename)) throw new Error("Invalid artifact filename");
  const response = await http.request<Blob>({ url: `/api/v1/documents/artifact/${filename}`,
    method: "GET", responseType: "blob", timeout: 30000, silent: true });
  const blob = response.data;
  if (!(blob instanceof Blob) || blob.type !== "application/json" || blob.size > 1024 * 1024) throw new Error("Invalid artifact response");
  return blob;
}
