import { documentChunkPath, documentChunksPath } from "@/constants/api-paths";
import { request } from "./http";
import { asRecord, clampWhole, count, text } from "./mapping";

/**
 * Chunk APIs (plan 04-18). Chunk text is user and document text: it is bounded and rendered as a text node only.
 * Mappers copy an explicit field list.
 */

export type ChunkOrigin = "parsed" | "edited" | "manual";
const ORIGINS: readonly string[] = ["parsed", "edited", "manual"];

/** A box on a page, in the page image's pixel space. */
export interface ChunkPosition {
  page: number;
  x0: number;
  x1: number;
  top: number;
  bottom: number;
}

export interface ChunkView {
  id: string;
  text: string;
  positions: ChunkPosition[];
  origin: ChunkOrigin;
  enabled: boolean;
}

export interface ChunkPage {
  items: ChunkView[];
  total: number;
  /** `{page: [width, height]}` of the pages the listed chunks reference. */
  pageSizes: Record<string, [number, number]>;
}

export interface ListChunksInput {
  datasetId: string;
  docId: string;
  page: number;
  size: number;
  keywords: string;
  /** Only chunks with this switch; undefined for both. */
  available?: boolean;
}

export const MAX_CHUNK_PAGE_SIZE = 100;
export const MAX_CHUNK_KEYWORDS_LENGTH = 128;
/** A text write waits on the embedding model (45 s, UI-SPEC HTTP client rules). */
export const CHUNK_WRITE_TIMEOUT_MS = 45000;

function toPosition(raw: unknown): ChunkPosition | null {
  const dto = asRecord(raw);
  const values = [dto.page, dto.x0, dto.x1, dto.top, dto.bottom];
  if (!values.every((value) => typeof value === "number" && Number.isFinite(value))) return null;
  return { page: dto.page as number, x0: dto.x0 as number, x1: dto.x1 as number, top: dto.top as number, bottom: dto.bottom as number };
}

export function toChunk(raw: unknown): ChunkView {
  const dto = asRecord(raw);
  const origin = text(dto.origin);
  return {
    id: text(dto.id),
    text: text(dto.text),
    positions: Array.isArray(dto.positions) ? dto.positions.map(toPosition).filter((p): p is ChunkPosition => p !== null) : [],
    origin: ORIGINS.includes(origin) ? (origin as ChunkOrigin) : "parsed",
    enabled: dto.enabled !== false,
  };
}

function toPageSizes(raw: unknown): Record<string, [number, number]> {
  const sizes: Record<string, [number, number]> = {};
  for (const [page, value] of Object.entries(asRecord(raw))) {
    if (Array.isArray(value) && value.length === 2 && value.every((n) => typeof n === "number" && Number.isFinite(n))) sizes[page] = [value[0] as number, value[1] as number];
  }
  return sizes;
}

/** GET .../documents/{doc}/chunks: one page. Silent: the page renders its own error state. */
export async function listChunks(input: ListChunksInput): Promise<ChunkPage> {
  const params: Record<string, string | number> = {
    page: clampWhole(input.page, 1, Number.MAX_SAFE_INTEGER),
    size: clampWhole(input.size, 1, MAX_CHUNK_PAGE_SIZE),
  };
  const keywords = input.keywords.slice(0, MAX_CHUNK_KEYWORDS_LENGTH);
  if (keywords !== "") params.keywords = keywords;
  if (input.available !== undefined) params.available = input.available ? 1 : 0;
  const data = asRecord(await request<unknown>({ url: documentChunksPath(input.datasetId, input.docId), method: "GET", params }, { silent: true }));
  return { items: Array.isArray(data.items) ? data.items.map(toChunk) : [], total: count(data.total), pageSizes: toPageSizes(data.page_sizes) };
}

/** POST .../chunks with `content_with_weight`: embeds first, then writes. Silent: the dialog shows the refusal. */
export async function createChunk(datasetId: string, docId: string, content: string): Promise<ChunkView> {
  const data = await request<unknown>(
    { url: documentChunksPath(datasetId, docId), method: "POST", data: { content_with_weight: content }, timeout: CHUNK_WRITE_TIMEOUT_MS },
    { silent: true },
  );
  return toChunk(data);
}

export interface ChunkChanges {
  text?: string;
  enabled?: boolean;
}

/**
 * PATCH .../chunks/{id}. A text change waits on the embedding model, so it gets 45 s; a switch alone uses the default
 * timeout. Only the keys given are sent. Silent: the editor shows the refusal.
 */
export async function updateChunk(datasetId: string, docId: string, chunkId: string, changes: ChunkChanges): Promise<ChunkView> {
  const data: Record<string, unknown> = {};
  if (changes.text !== undefined) data.content_with_weight = changes.text;
  if (changes.enabled !== undefined) data.available = changes.enabled;
  const config = { url: documentChunkPath(datasetId, docId, chunkId), method: "PATCH", data };
  return toChunk(await request<unknown>(changes.text !== undefined ? { ...config, timeout: CHUNK_WRITE_TIMEOUT_MS } : config, { silent: true }));
}
