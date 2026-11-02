import { datasetPath } from "@/constants/api-paths";
import { request } from "./http";
import { asRecord, count, text } from "./mapping";

export interface DatasetJob {
  id: string;
  type: "enrich";
  status: "running" | "done" | "failed" | "cancelled";
  total: number;
  completed: number;
  failed: number;
  progress: number;
  createdAt: number;
  updatedAt: number;
}

function mapJob(value: unknown): DatasetJob | null {
  const raw = asRecord(value);
  const run = text(raw.run);
  const status = ({ "1": "running", "2": "cancelled", "3": "done", "4": "failed" } as const)[run as "1" | "2" | "3" | "4"];
  if (!/^[0-9a-f]{32}$/.test(text(raw.id)) || raw.type !== "enrich" || !status) return null;
  return { id: text(raw.id), type: "enrich", status, total: count(raw.total),
    completed: count(raw.completed), failed: count(raw.failed), progress: typeof raw.progress === "number" && Number.isFinite(raw.progress) ? Math.min(1, Math.max(0, raw.progress)) : 0,
    createdAt: count(raw.created_at), updatedAt: count(raw.updated_at) };
}

export async function listDatasetJobs(datasetId: string, signal?: AbortSignal): Promise<DatasetJob[]> {
  const raw = asRecord(await request<unknown>({ url: `${datasetPath(datasetId)}/jobs`, method: "GET", signal }, { silent: true }));
  return Array.isArray(raw.items) ? raw.items.slice(0, 20).flatMap(item => { const job = mapJob(item); return job ? [job] : []; }) : [];
}

export async function startDatasetEnrichment(datasetId: string): Promise<DatasetJob> {
  const job = mapJob(await request<unknown>({ url: `${datasetPath(datasetId)}/jobs`, method: "POST", data: { type: "enrich" }, timeout: 30000 }, { silent: true }));
  if (!job) throw new Error("Invalid job response");
  return job;
}

export async function cancelDatasetJob(datasetId: string, jobId: string): Promise<DatasetJob> {
  const job = mapJob(await request<unknown>({ url: `${datasetPath(datasetId)}/jobs/${jobId}/cancel`, method: "POST" }, { silent: true }));
  if (!job) throw new Error("Invalid job response");
  return job;
}
