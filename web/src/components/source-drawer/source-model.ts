import type { AudioView } from "@/services/audio-features";
import type { SlideView } from "@/services/slide-features";
import { finiteScore, referenceChunk, type Reference, type SourceHit } from "@/services/chat-service";
import type { TableView } from "@/services/table-features";
import type { ChunkPosition } from "@/services/chunk-service";

export interface SourceView {
  tables?: TableView[];
  slide?: SlideView;
  audio?: AudioView;
  kind: "chat" | "hit"; number: number; chunkId: string; docId: string; docName: string; datasetId: string; content: string;
  positions: ChunkPosition[]; pageSizes: Record<string, [number, number]>;
  scores: { overall: number | null; term: number | null; vector: number | null; rerank: number | null };
}
function normalize(hit: SourceHit, kind: SourceView["kind"], number: number): SourceView {
  return { kind, number, chunkId: hit.chunkId, docId: hit.docId, docName: hit.docName, datasetId: hit.datasetId, content: hit.content,
    ...(hit.audio ? {audio:hit.audio} : {}),
    ...(hit.slide ? {slide:hit.slide} : {}),
    ...(hit.tables !== undefined ? { tables: hit.tables } : {}),
    positions: hit.positions.filter((position) => Number.isSafeInteger(position.page) && position.page > 0), pageSizes: hit.pageSizes,
    scores: { overall: finiteScore(hit.similarity), term: finiteScore(hit.termSimilarity), vector: finiteScore(hit.vectorSimilarity), rerank: finiteScore(hit.rerankSimilarity) } };
}
export function sourceFromReference(reference: Reference, index: number): SourceView | null {
  const chunk = referenceChunk(reference, index);
  return chunk && !chunk.unavailable ? normalize(chunk, "chat", chunk.index + 1) : null;
}
export function sourceFromHit(hit: SourceHit, rank: number): SourceView { return normalize(hit, "hit", rank); }
