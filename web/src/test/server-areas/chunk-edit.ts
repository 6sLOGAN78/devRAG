import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from "axios";
import type { AreaHandler, DatasetServer } from "../dataset-server";
import { chunkId, chunkStateOf, type ChunkRow } from "./chunks";

/**
 * Test-server area for the chunk editor (plan 04-31, R-167): POST adds a chunk by hand and PATCH with a text changes a
 * chunk's text, both only after the "embedding" succeeded, so a refused write leaves the stored row untouched (D-11).
 * The chunk store is the one of `chunks.ts`; a PATCH that carries only the switch is left to that area. Failures are
 * injected with `refuse`, which can carry the provider's own `detail` and a client timeout, neither of which the core
 * server's `forced` mechanism can express. Fake data only.
 */

export type EditKind = "create" | "update";

export interface Refusal {
  status?: number;
  reason?: string;
  /** The provider's own sentence, sent as `data.detail`. */
  detail?: string;
  /** The request ends in the client's timeout (`ECONNABORTED`) instead of an answer. */
  timeout?: boolean;
  /** Refuse this many times, then succeed. Default: every time. */
  times?: number;
}

interface EditState {
  refusals: Partial<Record<EditKind, Refusal>>;
  /** Longest text the "embedding model" accepts; longer text is refused with `chunk_too_long`. */
  limit: number;
  /** The texts that reached the "embedding model", in order. A refused text counts. */
  embedded: string[];
}

const editStateOf = (server: DatasetServer): EditState => server.areaState<EditState>("chunk-edit", () => ({ refusals: {}, limit: Number.POSITIVE_INFINITY, embedded: [] }));

/** Makes the next write of `kind` fail as described. */
export function refuse(server: DatasetServer, kind: EditKind, refusal: Refusal): void {
  editStateOf(server).refusals[kind] = { ...refusal };
}

/** Sets the longest text the model accepts. */
export function setTokenLimit(server: DatasetServer, limit: number): void {
  editStateOf(server).limit = limit;
}

/** The texts that were sent to the model, in order. */
export const embeddedTexts = (server: DatasetServer): string[] => editStateOf(server).embedded;

function answerFailure(config: InternalAxiosRequestConfig, refusal: Refusal): Promise<never> {
  if (refusal.timeout === true) return Promise.reject(new AxiosError("timeout of 45000ms exceeded", "ECONNABORTED", config));
  const status = refusal.status ?? 500;
  const data = { reason: refusal.reason, ...(refusal.detail === undefined ? {} : { detail: refusal.detail }) };
  const response = { data: { code: status, message: "refused", data }, status, statusText: String(status), headers: new AxiosHeaders(), config } as never;
  return Promise.reject(new AxiosError(`status ${status}`, "ERR_BAD_RESPONSE", config, null, response));
}

function nextRefusal(state: EditState, kind: EditKind): Refusal | undefined {
  const refusal = state.refusals[kind];
  if (refusal === undefined) return undefined;
  if (refusal.times !== undefined) {
    refusal.times -= 1;
    if (refusal.times <= 0) delete state.refusals[kind];
  }
  return refusal;
}

const CHUNKS_ROUTE = /^\/api\/v1\/datasets\/([^/]+)\/documents\/([^/]+)\/chunks(?:\/([^/]+))?$/;

export const handle: AreaHandler = ({ server, config, method, url, ok, failure }) => {
  const matched = CHUNKS_ROUTE.exec(url);
  if (!matched || (method !== "POST" && method !== "PATCH")) return undefined;
  const [, datasetId, docId, chunkKey] = matched as unknown as [string, string, string, string | undefined];
  if (server.datasets[datasetId] === undefined || !(server.documents[datasetId] ?? []).some((d) => d.id === docId)) return undefined;
  const sent = JSON.parse(String(config.data ?? "{}")) as Record<string, unknown>;
  const content = sent.content_with_weight;
  if (typeof content !== "string") return undefined;

  const state = editStateOf(server);
  const rows = (chunkStateOf(server).byDoc[docId] ??= []);
  const kind: EditKind = method === "POST" ? "create" : "update";
  if (method === "POST" && chunkKey !== undefined) return undefined;
  if (method === "PATCH" && chunkKey === undefined) return undefined;
  if (content.trim() === "") return failure({ status: 400, message: "empty", reason: "validation" });

  const row = chunkKey === undefined ? undefined : rows.find((r) => r.id === chunkKey);
  if (chunkKey !== undefined && row === undefined) return failure({ status: 404, message: "not found", reason: "not_found" });

  state.embedded.push(content);
  const refusal = nextRefusal(state, kind);
  if (refusal !== undefined) return answerFailure(config, refusal);
  if (content.length > state.limit) return failure({ status: 400, message: "too long", reason: "chunk_too_long" });

  if (row !== undefined) {
    row.text = content;
    if (row.origin === "parsed") row.origin = "edited";
    return ok(row);
  }
  const created: ChunkRow = { id: chunkId(rows.length + 1), text: content, positions: [], origin: "manual", enabled: true };
  rows.push(created);
  const list = server.documents[datasetId] ?? [];
  server.documents[datasetId] = list.map((d) => (d.id === docId ? { ...d, chunk_num: rows.length } : d));
  return ok(created);
};
