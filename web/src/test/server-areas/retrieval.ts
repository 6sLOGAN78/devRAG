import type { AreaHandler, DatasetServer } from "../dataset-server";

export const setHits = (server: DatasetServer, hits: Record<string, unknown>[]): void => { server.areaState("retrieval", () => ({ hits: [] as Record<string, unknown>[] })).hits = hits; };
export const handle: AreaHandler = ({ server, method, url, config, ok, failure }) => {
  if (method !== "POST" || url !== "/api/v1/datasets/search") return undefined;
  const body = JSON.parse(String(config.data ?? "{}")) as Record<string, unknown>;
  const ids = Array.isArray(body.dataset_ids) ? body.dataset_ids : [];
  if (!ids.length) return failure({ status: 400, message: "datasets required", reason: "fields_invalid" });
  if (ids.some((id) => {
    const row = server.datasets[String(id)]; return !row || row.permission !== "team" && row.created_by !== server.uploader;
  })) return failure({ status: 404, message: "dataset not found", reason: "dataset_not_found" });
  const words = String(body.question ?? "").toLowerCase().split(/\W+/).filter(Boolean);
  const weight = Number(body.vector_similarity_weight ?? 0.3), threshold = Number(body.similarity_threshold ?? 0.2);
  const rerank = typeof body.rerank_id === "string" && body.rerank_id !== "";
  const hits = server.areaState("retrieval", () => ({ hits: [] as Record<string, unknown>[] })).hits.filter((h) => ids.includes(h.dataset_id)).map((h) => {
    const term = words.length ? words.filter((w) => String(h.content).toLowerCase().includes(w)).length / words.length : 0;
    const vector = Number(h.vector_similarity ?? 0.5), rank = Number(h.rerank_similarity ?? term);
    return { doc_id: "doc", doc_name: "Document", positions: [], page_sizes: {}, ...h, term_similarity: term, vector_similarity: vector,
      similarity: (1 - weight) * term + weight * (rerank ? rank : vector), ...(rerank ? { rerank_similarity: rank } : {}) };
  }).filter((h) => h.similarity >= threshold).sort((a, b) => b.similarity - a.similarity);
  const page = Math.max(1, Number(body.page) || 1), size = Math.max(1, Number(body.size) || 10);
  return ok({ chunks: hits.slice((page - 1) * size, page * size), total: hits.length, rerank_applied: rerank, timings: { search_ms: 1, rerank_ms: rerank ? 1 : 0 } });
};
