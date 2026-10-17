import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { documentDetailKey, documentsQueryKey } from "./use-document-request";
import { chunksKey, chunksKeyRoot, useChunkRefresh, useChunksRequest, useCreateChunkRequest, useUpdateChunkRequest } from "./use-chunk-request";
import { datasetQueryKey } from "./use-knowledge-request";

const USER: SessionUser = {
  id: "u1",
  nickname: "Ada",
  email: "ada@example.test",
  avatar: "",
  language: "English",
  colorSchema: "Bright",
  tenantId: "t1",
  tenantName: "Ada's workspace",
  role: "owner",
  isSuperuser: false,
};

const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
const ok = (config: InternalAxiosRequestConfig, data: unknown) =>
  ({ data: { code: 0, message: "", data }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

const adapter: AxiosAdapter = (config) => {
  calls.push(config);
  const key = `${String(config.method).toUpperCase()} ${config.url}`;
  if (key === "GET /v1/tenant/list") return Promise.resolve(ok(config, []));
  if (key === "GET /api/v1/datasets/kb1/documents/d1/chunks") return Promise.resolve(ok(config, { items: [{ id: "c1", text: "hello" }], total: 1 }));
  if (key === "POST /api/v1/datasets/kb1/documents/d1/chunks") return Promise.resolve(ok(config, { id: "c2", text: "new", origin: "manual" }));
  if (key === "PATCH /api/v1/datasets/kb1/documents/d1/chunks/c1") return Promise.resolve(ok(config, { id: "c1", text: "edited", origin: "edited" }));
  return Promise.reject(new Error(`unexpected ${key}`));
};

let client: QueryClient;
const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;

beforeEach(() => {
  calls = [];
  http.defaults.adapter = adapter;
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  registerQueryClient(client);
  useUserStore.setState({ user: USER });
  useWorkspaceStore.getState().reset();
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
});

describe("chunk query keys", () => {
  it("sit under the workspace, dataset and document", () => {
    expect(chunksKey("t1", "kb1", "d1", 2, "rev", "on")).toEqual(["ws", "t1", "chunks", "kb1", "d1", 2, "rev", "on"]);
    expect(chunksKeyRoot("t1", "kb1", "d1")).toEqual(["ws", "t1", "chunks", "kb1", "d1"]);
  });
});

describe("useChunksRequest", () => {
  it("loads a page with size 20, keeps the previous page and does not poll", async () => {
    const { result } = renderHook(() => useChunksRequest({ datasetId: "kb1", docId: "d1", page: 1, keywords: "", show: "all" }), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls.find((c) => c.url?.endsWith("/chunks"))?.params).toMatchObject({ page: 1, size: 20 });
    const query = client.getQueryCache().find({ queryKey: chunksKey("t1", "kb1", "d1", 1, "", "all") });
    expect(query?.observers[0]?.options.refetchInterval).toBeFalsy();
  });

  it("maps show to the available filter", async () => {
    const { result } = renderHook(() => useChunksRequest({ datasetId: "kb1", docId: "d1", page: 1, keywords: "", show: "off" }), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls.find((c) => c.url?.endsWith("/chunks"))?.params).toMatchObject({ available: 0 });
  });
});

describe("useChunkRefresh", () => {
  it("refetches the chunks when the chunk count changes and when run leaves 1", () => {
    const key = chunksKey("t1", "kb1", "d1", 1, "", "all");
    client.setQueryData(key, { items: [], total: 0, pageSizes: {} });
    const detail = (chunkCount: number, run: string) => ({ id: "d1", datasetId: "kb1", chunkCount, run }) as never;
    const { rerender } = renderHook(({ d }) => useChunkRefresh(d), { wrapper, initialProps: { d: detail(0, "1") } });
    expect(client.getQueryState(key)?.isInvalidated).toBe(false);
    rerender({ d: detail(5, "1") });
    expect(client.getQueryState(key)?.isInvalidated).toBe(true);
    client.setQueryData(key, { items: [], total: 0, pageSizes: {} });
    expect(client.getQueryState(key)?.isInvalidated).toBe(false);
    rerender({ d: detail(5, "3") });
    expect(client.getQueryState(key)?.isInvalidated).toBe(true);
  });
});

describe("chunk mutations refresh in onSettled", () => {
  const seed = () => {
    const keys = {
      chunks: chunksKey("t1", "kb1", "d1", 1, "", "all"),
      detail: documentDetailKey("t1", "kb1", "d1"),
      documents: documentsQueryKey("t1", "kb1", 1, ""),
      dataset: datasetQueryKey("t1", "kb1"),
      otherDoc: chunksKey("t1", "kb1", "d2", 1, "", "all"),
    };
    for (const key of Object.values(keys)) client.setQueryData(key, { seeded: true });
    return keys;
  };
  const expectRefreshed = (keys: ReturnType<typeof seed>) => {
    expect(client.getQueryState(keys.chunks)?.isInvalidated).toBe(true);
    expect(client.getQueryState(keys.detail)?.isInvalidated).toBe(true);
    expect(client.getQueryState(keys.documents)?.isInvalidated).toBe(true);
    expect(client.getQueryState(keys.dataset)?.isInvalidated).toBe(true);
    expect(client.getQueryState(keys.otherDoc)?.isInvalidated).toBe(false);
  };

  it("create", async () => {
    const keys = seed();
    const { result } = renderHook(() => useCreateChunkRequest(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ datasetId: "kb1", docId: "d1", content: "new" });
    });
    expectRefreshed(keys);
  });

  it("update, with the 45 s timeout for a text change", async () => {
    const keys = seed();
    const { result } = renderHook(() => useUpdateChunkRequest(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ datasetId: "kb1", docId: "d1", chunkId: "c1", changes: { text: "edited" } });
    });
    expectRefreshed(keys);
    expect(calls.find((c) => c.method === "patch")?.timeout).toBe(45000);
  });
});
