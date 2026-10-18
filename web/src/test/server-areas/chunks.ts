import type { AreaHandler, DatasetServer } from "../dataset-server";

/**
 * Test-server area for the chunk inspector (R-167): the chunk list of a document (search, the `available` filter, paging,
 * `page_sizes`), the PATCH of a chunk's switch and the page image as a one-pixel PNG. The chunks of each document live in
 * `server.areaState("chunks", ...)`, so a reset clears them. Plan 04-31 adds its own writes on the same store. Fake data only.
 */

export interface ChunkPositionRow {
  page: number;
  x0: number;
  x1: number;
  top: number;
  bottom: number;
}

export interface ChunkRow {
  id: string;
  text: string;
  positions: ChunkPositionRow[];
  origin: "parsed" | "edited" | "manual";
  enabled: boolean;
}

export interface ChunksState {
  /** Chunks per document id, in document order. */
  byDoc: Record<string, ChunkRow[]>;
  /** `{page: [width, height]}` per document id; a page with no entry is A4 at 72 dpi. */
  sizes: Record<string, Record<string, [number, number]>>;
}

export const A4_POINTS: [number, number] = [595, 842];

/** The shared chunk store. Exported for plan 04-31. */
export const chunkStateOf = (server: DatasetServer): ChunksState => server.areaState<ChunksState>("chunks", () => ({ byDoc: {}, sizes: {} }));

export const chunkId = (n: number): string => `chunk${String(n).padStart(27, "0")}`;

/** A parsed chunk with one box on `page` unless `positions` says otherwise. */
export function chunkRow(n: number, over: Partial<ChunkRow> = {}): ChunkRow {
  return {
    id: chunkId(n),
    text: `Chunk text number ${n}`,
    positions: [{ page: 1, x0: 59.5, top: 84.2, x1: 297.5, bottom: 168.4 }],
    origin: "parsed",
    enabled: true,
    ...over,
  };
}

/** Replaces the chunks of a document. */
export function setChunks(server: DatasetServer, docId: string, rows: ChunkRow[], sizes?: Record<string, [number, number]>): void {
  const state = chunkStateOf(server);
  state.byDoc[docId] = rows;
  if (sizes) state.sizes[docId] = sizes;
}

export const chunksOf = (server: DatasetServer, docId: string): ChunkRow[] => chunkStateOf(server).byDoc[docId] ?? [];

/** The one-pixel PNG that stands in for a rendered page. */
function pngBlob(): Blob {
  const bytes = Uint8Array.from(atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="), (c) => c.charCodeAt(0));
  return new Blob([bytes], { type: "image/png" });
}

const CHUNKS_ROUTE = /^\/api\/v1\/datasets\/([^/]+)\/documents\/([^/]+)\/chunks(?:\/([^/]+))?$/;
const IMAGE_ROUTE = /^\/api\/v1\/datasets\/([^/]+)\/documents\/([^/]+)\/pages\/(\d+)\/image$/;

const ownsDocument = (server: DatasetServer, datasetId: string, docId: string): boolean =>
  server.datasets[datasetId] !== undefined && (server.documents[datasetId] ?? []).some((d) => d.id === docId);

export const handle: AreaHandler = ({ server, config, method, url, params, ok, failure }) => {
  const image = IMAGE_ROUTE.exec(url);
  if (image && method === "GET") {
    if (!ownsDocument(server, image[1] as string, image[2] as string)) return undefined;
    return { data: pngBlob(), status: 200, statusText: "OK", headers: { "content-type": "image/png" }, config };
  }
  const matched = CHUNKS_ROUTE.exec(url);
  if (!matched) return undefined;
  const [, datasetId, docId, chunkKey] = matched as unknown as [string, string, string, string | undefined];
  if (!ownsDocument(server, datasetId, docId)) return undefined;
  const state = chunkStateOf(server);
  const rows = (state.byDoc[docId] ??= []);

  if (method === "GET" && chunkKey === undefined) {
    const words = String(params.keywords ?? "")
      .toLowerCase()
      .split(/\s+/)
      .filter((w) => w !== "");
    const available = params.available === undefined ? null : Number(params.available) === 1;
    const matching = rows.filter((row) => (available === null || row.enabled === available) && words.every((w) => row.text.toLowerCase().includes(w)));
    const size = Number(params.size);
    const page = Number(params.page);
    const items = matching.slice((page - 1) * size, page * size);
    const sizes: Record<string, [number, number]> = {};
    for (const row of items) for (const position of row.positions) sizes[String(position.page)] = state.sizes[docId]?.[String(position.page)] ?? A4_POINTS;
    return ok({ items, total: matching.length, page_sizes: sizes });
  }

  if (method === "PATCH" && chunkKey !== undefined) {
    const row = rows.find((r) => r.id === chunkKey);
    if (!row) return failure({ status: 404, message: "not found", reason: "not_found" });
    const sent = JSON.parse(String(config.data)) as Record<string, unknown>;
    if (typeof sent.available === "boolean") row.enabled = sent.available;
    return ok(row);
  }
  return undefined;
};
