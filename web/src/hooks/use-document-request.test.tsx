import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { documentsKeyRoot, documentsQueryKey, useDeleteDocumentsRequest, useDocumentsRequest } from "./use-document-request";
import { datasetQueryKey, datasetsKeyRoot } from "./use-knowledge-request";

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
  if (key === "GET /api/v1/datasets/kb1/documents") return Promise.resolve(ok(config, { items: [], total: 0 }));
  if (key === "DELETE /api/v1/datasets/kb1/documents") return Promise.resolve(ok(config, { deleted: 1 }));
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

describe("document query keys (TEN-13)", () => {
  it("sit under the workspace and the dataset", () => {
    expect(documentsKeyRoot("t1", "kb1")).toEqual(["ws", "t1", "documents", "kb1"]);
    expect(documentsQueryKey("t1", "kb1", 2, "rep")).toEqual(["ws", "t1", "documents", "kb1", 2, "rep"]);
  });
});

describe("useDocumentsRequest", () => {
  it("loads one page of the dataset's documents under the active workspace's key", async () => {
    const { result } = renderHook(() => useDocumentsRequest({ datasetId: "kb1", page: 1, keywords: "" }), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ items: [], total: 0 });
    expect(calls.find((c) => c.url === "/api/v1/datasets/kb1/documents")?.params).toEqual({ page: 1, page_size: 20 });
    expect(client.getQueryData(documentsQueryKey("t1", "kb1", 1, ""))).toBeDefined();
  });

  it("stays idle without a dataset id", () => {
    const { result } = renderHook(() => useDocumentsRequest({ datasetId: undefined, page: 1, keywords: "" }), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useDeleteDocumentsRequest (DOC-14)", () => {
  it("deletes, then invalidates the documents and both dataset keys of the active workspace only", async () => {
    const keys = {
      documents: documentsQueryKey("t1", "kb1", 1, ""),
      otherDataset: documentsQueryKey("t1", "kb2", 1, ""),
      list: [...datasetsKeyRoot("t1"), 1, ""],
      detail: datasetQueryKey("t1", "kb1"),
      otherWorkspace: documentsQueryKey("t2", "kb1", 1, ""),
    };
    for (const key of Object.values(keys)) client.setQueryData(key, { seeded: true });
    const { result } = renderHook(() => useDeleteDocumentsRequest(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ datasetId: "kb1", ids: ["d1"] });
    });
    expect(client.getQueryState(keys.documents)?.isInvalidated).toBe(true);
    expect(client.getQueryState(keys.list)?.isInvalidated).toBe(true);
    expect(client.getQueryState(keys.detail)?.isInvalidated).toBe(true);
    expect(client.getQueryState(keys.otherDataset)?.isInvalidated).toBe(false);
    expect(client.getQueryState(keys.otherWorkspace)?.isInvalidated).toBe(false);
  });
});
