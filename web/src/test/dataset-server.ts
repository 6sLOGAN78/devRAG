/// <reference types="vite/client" />
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";

/**
 * An in-memory server for the dataset workspace tests, shaped like the APIs of plans 03-14, 03-16, 03-17 and 03-18:
 * the dataset detail (with `upload_limits`), the paged document list, the all-or-nothing document and dataset deletes,
 * the one-file upload and the membership list. Fake data only. Tests set `forced` to make one `METHOD url` fail.
 */
export const DATASET_ID = "0123456789abcdef0123456789abcdef";
export const OTHER_DATASET_ID = "fedcba9876543210fedcba9876543210";
export const UPDATED = Date.UTC(2026, 9, 5, 12, 0, 0);

export interface MembershipRow {
  tenant_id: string;
  tenant_name: string;
  owner_nickname: string;
  owner_avatar: string;
  role: string;
  joined_time: string;
}

export const membershipRow = (tenant_id: string, tenant_name: string, role: string, owner_nickname = "Owner"): MembershipRow => ({
  tenant_id,
  tenant_name,
  owner_nickname,
  owner_avatar: "",
  role,
  joined_time: "2026-10-01T12:00:00Z",
});

/** The shape the membership store expects, from the wire rows. */
export const storedMemberships = (rows: readonly MembershipRow[]) =>
  rows.map((r) => ({ tenantId: r.tenant_id, tenantName: r.tenant_name, ownerNickname: r.owner_nickname, ownerAvatar: r.owner_avatar, role: r.role, joinedTime: r.joined_time }));

export interface DatasetRow {
  id: string;
  name: string;
  description: string;
  permission: string;
  embd_id: string;
  embedding_dimension: number;
  created_by: string;
  tenant_id: string;
  update_time: number;
  upload_limits?: { max_file_bytes: number; max_files_per_request: number; max_documents: number; allowed_extensions: string[] };
}

export interface DocumentRow {
  id: string;
  name: string;
  size: number;
  type: string;
  suffix: string;
  run: string;
  progress: number;
  dataset_id: string;
  created_by: string;
  parser_id: string;
  chunk_num: number;
  update_time: number;
  create_time: number;
}

export const datasetRow = (over: Partial<DatasetRow> = {}): DatasetRow => ({
  id: DATASET_ID,
  name: "Reports",
  description: "Quarterly reports",
  permission: "team",
  embd_id: "embed-one@OpenRouter",
  embedding_dimension: 8,
  created_by: "u1",
  tenant_id: "t1",
  update_time: UPDATED,
  ...over,
});

export const documentRow = (n: number, over: Partial<DocumentRow> = {}, datasetId = DATASET_ID): DocumentRow => ({
  id: `doc${String(n).padStart(29, "0")}`,
  name: `report-${String(n).padStart(2, "0")}.pdf`,
  size: 1536,
  type: "pdf",
  suffix: "pdf",
  run: "0",
  progress: 0,
  dataset_id: datasetId,
  created_by: "u1",
  parser_id: "naive",
  chunk_num: 0,
  update_time: UPDATED,
  create_time: UPDATED,
  ...over,
});

export interface Forced {
  status: number;
  message: string;
  reason?: string;
  data?: Record<string, unknown>;
}

export const ok = (config: InternalAxiosRequestConfig, data: unknown) =>
  ({ data: { code: 0, message: "", data }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

export function failure(config: InternalAxiosRequestConfig, f: Forced) {
  const data = f.reason === undefined && f.data === undefined ? null : { ...f.data, ...(f.reason === undefined ? {} : { reason: f.reason }) };
  const response = { data: { code: f.status, message: f.message, data }, status: f.status, statusText: String(f.status), headers: new AxiosHeaders(), config } as never;
  return Promise.reject(new AxiosError(`status ${f.status}`, "ERR_BAD_RESPONSE", config, null, response));
}

export interface AreaContext {
  server: DatasetServer;
  config: InternalAxiosRequestConfig;
  method: string;
  url: string;
  params: Record<string, string | number>;
  ok: (data: unknown) => unknown;
  failure: (forced: Forced) => Promise<never>;
}

/** Returns `undefined` to pass, anything else (or a promise of it) answers the request. */
export type AreaHandler = (ctx: AreaContext) => unknown;

export interface DatasetServer {
  /** Register a handler that answers before the core routes. */
  use: (handler: AreaHandler) => void;
  /** Per-server state for area handlers, cleared by `reset()`. */
  areaState: <T>(key: string, init: () => T) => T;
  calls: InternalAxiosRequestConfig[];
  forced: Record<string, Forced>;
  /** Requests whose `METHOD url` key is here wait for the promise before they are answered. */
  holds: Record<string, Promise<void>>;
  memberships: MembershipRow[];
  datasets: Record<string, DatasetRow>;
  documents: Record<string, DocumentRow[]>;
  /** `created_by` of documents stored by the upload endpoint. */
  uploader: string;
  adapter: AxiosAdapter;
  reset: () => void;
  callsTo: (method: string, url: string) => InternalAxiosRequestConfig[];
}

const areaModules = import.meta.glob<{ handle?: AreaHandler }>("./server-areas/*.ts", { eager: true });

export function createDatasetServer(): DatasetServer {
  const handlers: AreaHandler[] = [];
  const state = new Map<string, unknown>();
  const server: DatasetServer = {
    use: (handler) => {
      handlers.push(handler);
    },
    areaState: <T,>(key: string, init: () => T): T => {
      if (!state.has(key)) state.set(key, init());
      return state.get(key) as T;
    },
    calls: [],
    forced: {},
    holds: {},
    memberships: [],
    datasets: {},
    documents: {},
    uploader: "u1",
    adapter: undefined as never,
    reset: () => {
      server.calls = [];
      server.forced = {};
      server.holds = {};
      server.memberships = [];
      server.datasets = {};
      server.documents = {};
      server.uploader = "u1";
      state.clear();
    },
    callsTo: (method, url) => server.calls.filter((c) => c.method?.toUpperCase() === method && c.url === url),
  };

  const detailOf = (row: DatasetRow) => ({ ...row, doc_num: (server.documents[row.id] ?? []).length, chunk_num: 0, token_num: 0, language: "English", parser_id: "naive", create_time: UPDATED });

  async function serve(config: InternalAxiosRequestConfig): Promise<unknown> {
    const method = String(config.method).toUpperCase();
    const url = config.url ?? "";
    const key = `${method} ${url}`;
    const held = server.holds[key];
    if (held) await held;
    const stop = server.forced[key];
    if (stop) return failure(config, stop);
    const params = (config.params ?? {}) as Record<string, string | number>;
    for (const handler of handlers) {
      const answer = await handler({ server, config, method, url, params, ok: (data) => ok(config, data), failure: (f) => failure(config, f) as Promise<never> });
      if (answer !== undefined) return answer;
    }
    if (key === "GET /v1/tenant/list") return ok(config, server.memberships);
    if (key === "GET /api/v1/models") return ok(config, []);
    if (key === "GET /api/v1/models/default") return ok(config, { chat: "", embedding: "" });
    if (key === "POST /api/v1/documents/upload") {
      const id = String(params.dataset_id ?? "");
      const form = config.data as FormData;
      const file = form.get("file") as File;
      const list = (server.documents[id] ??= []);
      const row = documentRow(list.length + 100, { name: file.name, size: file.size, created_by: server.uploader }, id);
      list.unshift(row);
      return ok(config, [row]);
    }
    if (key === "DELETE /api/v1/datasets") {
      const sent = JSON.parse(String(config.data)) as { ids: string[] };
      for (const id of sent.ids) delete server.datasets[id];
      return ok(config, { deleted: sent.ids });
    }
    const docs = /^\/api\/v1\/datasets\/([^/]+)\/documents$/.exec(url);
    if (docs) {
      const id = docs[1] as string;
      if (!server.datasets[id]) return failure(config, { status: 404, message: "not found" });
      const list = (server.documents[id] ??= []);
      if (method === "GET") {
        const keywords = String(params.keywords ?? "").toLowerCase();
        const matching = list.filter((d) => d.name.toLowerCase().includes(keywords));
        const size = Number(params.page_size);
        const page = Number(params.page);
        return ok(config, { items: matching.slice((page - 1) * size, page * size), total: matching.length });
      }
      if (method === "DELETE") {
        const sent = JSON.parse(String(config.data)) as { ids: string[] };
        server.documents[id] = list.filter((d) => !sent.ids.includes(d.id));
        return ok(config, { deleted: sent.ids.length });
      }
    }
    const one = /^\/api\/v1\/datasets\/([^/]+)$/.exec(url);
    if (one) {
      const row = server.datasets[one[1] as string];
      if (!row) return failure(config, { status: 404, message: "not found" });
      if (method === "GET") return ok(config, detailOf(row));
      if (method === "PUT") {
        Object.assign(row, JSON.parse(String(config.data)) as Record<string, unknown>);
        return ok(config, detailOf(row));
      }
    }
    return failure(config, { status: 404, message: "not found" });
  }

  for (const path of Object.keys(areaModules).sort()) {
    const handle = areaModules[path]?.handle;
    if (typeof handle !== "function") throw new Error(`test server area ${path} must export handle`);
    server.use(handle);
  }

  server.adapter = (config) => {
    server.calls.push(config);
    return serve(config) as never;
  };
  return server;
}
