import { beforeEach, describe, expect, it, vi } from "vitest";
import { request } from "./http";
import { RETRIEVAL_TIMEOUT_MS, searchDataset } from "./retrieval-service";

vi.mock("./http", () => ({ request: vi.fn() }));
beforeEach(() => vi.mocked(request).mockReset());
describe("retrieval service", () => {
  it("sends one dataset and explicit controls with a silent 45 s timeout", async () => {
    vi.mocked(request).mockResolvedValue({ total: 1, chunks: [{ chunk_id: "c", similarity: "NaN", rerank_similarity: 0.4 }], rerank_applied: true, timings: { embed_ms: 2, rerank_ms: 8, search_ms: Infinity } });
    const result = await searchDataset({ datasetId: "d", question: "q", similarityThreshold: 0.2, vectorSimilarityWeight: 0.8, rerankId: "r", page: 1, size: 10 });
    expect(RETRIEVAL_TIMEOUT_MS).toBe(45000);
    expect(request).toHaveBeenCalledWith(expect.objectContaining({ url: "/api/v1/datasets/search", timeout: 45000, data: { dataset_ids: ["d"], question: "q", similarity_threshold: 0.2, vector_similarity_weight: 0.8, rerank_id: "r", page: 1, size: 10 } }), { silent: true });
    expect(result).toMatchObject({ total: 1, rerankApplied: true, hits: [{ chunkId: "c", similarity: null, rerankSimilarity: 0.4 }], timings: { embedMs: 2, rerankMs: 8, searchMs: null } });
  });
  it("omits an unset reranker and tolerates malformed response fields", async () => {
    vi.mocked(request).mockResolvedValue(null); expect(await searchDataset({ datasetId: "d", question: "q" })).toMatchObject({ hits: [], total: 0 });
    expect(vi.mocked(request).mock.calls[0]?.[0].data).not.toHaveProperty("rerank_id");
  });
});
