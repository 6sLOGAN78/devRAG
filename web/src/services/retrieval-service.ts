import { datasetSearchPath } from "@/constants/api-paths";
import { finiteScore, toSourceHit, type SourceHit } from "./chat-service";
import { request } from "./http";
import { asRecord, clampWhole, count } from "./mapping";

export type HitView = SourceHit;
export interface RetrievalInput {
  datasetId: string; question: string; similarityThreshold?: number; vectorSimilarityWeight?: number;
  rerankId?: string; page?: number; size?: number;
  tenantId?: string;
}
export interface RetrievalPage {
  total: number; hits: HitView[]; rerankApplied: boolean; timings: { embedMs: number | null; searchMs: number | null; rerankMs: number | null };
}
export const RETRIEVAL_TIMEOUT_MS = 45000;
export async function searchDataset(input: RetrievalInput): Promise<RetrievalPage> {
  const data = {
    dataset_ids: [input.datasetId], question: input.question,
    similarity_threshold: input.similarityThreshold ?? 0.2, vector_similarity_weight: input.vectorSimilarityWeight ?? 0.3,
    ...(input.rerankId ? { rerank_id: input.rerankId } : {}), page: clampWhole(input.page ?? 1, 1, Number.MAX_SAFE_INTEGER), size: clampWhole(input.size ?? 10, 1, 100),
    ...(input.tenantId ? { tenant_id: input.tenantId } : {}),
  };
  const d = asRecord(await request({ url: datasetSearchPath, method: "POST", data, timeout: RETRIEVAL_TIMEOUT_MS }, { silent: true }));
  const timing = asRecord(d.timings);
  return {
    total: count(d.total), hits: Array.isArray(d.chunks) ? d.chunks.map(toSourceHit) : [], rerankApplied: d.rerank_applied === true,
    timings: { embedMs: finiteScore(timing.embed_ms), searchMs: finiteScore(timing.search_ms), rerankMs: finiteScore(timing.rerank_ms) },
  };
}
