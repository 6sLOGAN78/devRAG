import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { setAuthorization } from "@/utils/authorization";
import { datasetQueryKey, datasetsQueryKey, useCreateDatasetRequest, useDatasetRequest, useDatasetsRequest } from "./use-knowledge-request";

// Real hooks, services and HTTP client against an in-memory server: each workspace has its own datasets, and the
// membership list gives the user a second workspace to switch to.
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

const MEMBERSHIP = { tenant_id: "t2", tenant_name: "Grace's workspace", owner_nickname: "Grace", owner_avatar: "", role: "admin", joined_time: "2026-01-01T00:00:00Z" };

const dto = (id: string, name: string, tenantId: string) => ({
  id,
  name,
  description: "",
  avatar: "",
  language: "English",
  permission: "me",
  embd_id: "embed-one@OpenRouter",
  embedding_dimension: 8,
  parser_id: "naive",
  parser_config: {},
  doc_num: 0,
  chunk_num: 0,
  token_num: 0,
  tenant_id: tenantId,
  created_by: "u1",
  create_time: 1,
  update_time: 2,
  upload_limits: { max_file_bytes: 1024, max_files_per_request: 5, max_documents: 10, allowed_extensions: ["pdf"] },
});

const originalAdapter = http.defaults.adapter;
let calls: InternalAxiosRequestConfig[] = [];
let failList = false;

const ok = (config: InternalAxiosRequestConfig, data: unknown) =>
  ({ data: { code: 0, message: "", data }, status: 200, statusText: "OK", headers: new AxiosHeaders(), config }) as never;

function serve(config: InternalAxiosRequestConfig): unknown {
  const key = `${String(config.method).toUpperCase()} ${config.url}`;
  if (key === "GET /v1/tenant/list") return ok(config, [MEMBERSHIP]);
  if (key === "GET /api/v1/datasets") {
    if (failList) {
      const response = { data: { code: 503, message: "busy", data: null }, status: 503, statusText: "503", headers: new AxiosHeaders(), config } as never;
      return Promise.reject(new AxiosError("status 503", "ERR_BAD_RESPONSE", config, null, response));
    }
    const tenant = String((config.params as { tenant_id: string }).tenant_id);
    return ok(config, { items: [dto(`kb-${tenant}`, `Datasets of ${tenant}`, tenant)], total: 1 });
  }
  if (key === "GET /api/v1/datasets/kb-t1") return ok(config, dto("kb-t1", "Datasets of t1", "t1"));
  if (key === "POST /api/v1/datasets") {
    const body = JSON.parse(String(config.data)) as { tenant_id: string; name: string };
    return ok(config, dto("kb-new", body.name, body.tenant_id));
  }
  return Promise.reject(new Error(`unexpected ${key}`));
}

const adapter: AxiosAdapter = async (config) => {
  calls.push(config);
  return (await Promise.resolve(serve(config))) as never;
};

const listCalls = () => calls.filter((c) => c.url === "/api/v1/datasets" && c.method?.toUpperCase() === "GET");

function makeClient(retry?: false): QueryClient {
  const client = new QueryClient(retry === false ? { defaultOptions: { queries: { retry: false } } } : {});
  registerQueryClient(client);
  return client;
}

function wrapperFor(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  calls = [];
  failList = false;
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
  useUserStore.getState().setUser(USER);
  useWorkspaceStore.getState().initialise("u1", "t1", [
    { tenantId: "t2", tenantName: "Grace's workspace", ownerNickname: "Grace", ownerAvatar: "", role: "admin", joinedTime: "2026-01-01T00:00:00Z" },
  ]);
  setAuthorization("tok-session");
  http.defaults.adapter = adapter;
});
afterEach(() => {
  http.defaults.adapter = originalAdapter;
  useUserStore.getState().reset();
  useWorkspaceStore.getState().reset();
});

describe("dataset query keys (TEN-13, D-26)", () => {
  it("start with the workspace so one workspace never reads another's cache", () => {
    expect(datasetsQueryKey("t1", 2, "x").slice(0, 2)).toEqual(["ws", "t1"]);
    expect(datasetQueryKey("t1", "kb1").slice(0, 2)).toEqual(["ws", "t1"]);
    expect(datasetsQueryKey("t1", 2, "x")).not.toEqual(datasetsQueryKey("t2", 2, "x"));
    expect(datasetsQueryKey("t1", 2, "x")).not.toEqual(datasetsQueryKey("t1", 3, "x"));
    expect(datasetsQueryKey("t1", 2, "x")).not.toEqual(datasetsQueryKey("t1", 2, "y"));
  });
});

describe("useDatasetsRequest", () => {
  it("lists the active workspace's datasets with its tenant id, page and keywords", async () => {
    const client = makeClient(false);
    const { result } = renderHook(() => useDatasetsRequest({ page: 2, keywords: "rep" }), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(result.current.data?.items[0]?.name).toBe("Datasets of t1"));
    expect(listCalls()).toHaveLength(1);
    expect(listCalls()[0]?.params).toEqual({ tenant_id: "t1", page: 2, page_size: 12, keywords: "rep" });
    expect(client.getQueryData(datasetsQueryKey("t1", 2, "rep"))).toBeDefined();
  });

  it("never serves the first workspace's data to the second", async () => {
    const client = makeClient(false);
    const { result } = renderHook(() => useDatasetsRequest({ page: 1, keywords: "" }), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(result.current.data?.items[0]?.name).toBe("Datasets of t1"));

    act(() => useWorkspaceStore.getState().setActive("t2"));
    await waitFor(() => expect(result.current.data?.items[0]?.name).toBe("Datasets of t2"));

    expect(listCalls().map((c) => (c.params as { tenant_id: string }).tenant_id)).toEqual(["t1", "t2"]);
    expect(client.getQueryData(datasetsQueryKey("t1", 1, ""))).toBeDefined();
    expect(client.getQueryData(datasetsQueryKey("t2", 1, ""))).toBeDefined();
  });

  it("does not retry a refusal: one request, then the error", async () => {
    failList = true;
    // A client with the library defaults: only the hook's own retry: false keeps this to a single request.
    const client = makeClient();
    const { result } = renderHook(() => useDatasetsRequest({ page: 1, keywords: "" }), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(listCalls()).toHaveLength(1);
  });

  it("sends nothing while signed out", async () => {
    useUserStore.getState().reset();
    useWorkspaceStore.getState().reset();
    const client = makeClient(false);
    const { result } = renderHook(() => useDatasetsRequest({ page: 1, keywords: "" }), { wrapper: wrapperFor(client) });
    expect(result.current.fetchStatus).toBe("idle");
    expect(listCalls()).toHaveLength(0);
  });
});

describe("useDatasetRequest", () => {
  it("opens one dataset with its upload limits under the active workspace's key", async () => {
    const client = makeClient(false);
    const { result } = renderHook(() => useDatasetRequest("kb-t1"), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(result.current.data?.name).toBe("Datasets of t1"));
    expect(result.current.data?.uploadLimits?.allowedExtensions).toEqual(["pdf"]);
    expect(client.getQueryData(datasetQueryKey("t1", "kb-t1"))).toBeDefined();
  });

  it("stays idle without an id", () => {
    const client = makeClient(false);
    const { result } = renderHook(() => useDatasetRequest(undefined), { wrapper: wrapperFor(client) });
    expect(result.current.fetchStatus).toBe("idle");
    expect(calls.filter((c) => c.url?.startsWith("/api/v1/datasets/"))).toHaveLength(0);
  });
});

describe("useCreateDatasetRequest (KB-01)", () => {
  it("invalidates the active workspace's list keys only", async () => {
    const client = makeClient(false);
    client.setQueryData(datasetsQueryKey("t1", 1, ""), { items: [], total: 0 });
    client.setQueryData(datasetsQueryKey("t1", 2, "x"), { items: [], total: 0 });
    client.setQueryData(datasetsQueryKey("t2", 1, ""), { items: [], total: 0 });
    const { result } = renderHook(() => useCreateDatasetRequest(), { wrapper: wrapperFor(client) });

    await act(async () => {
      await result.current.mutateAsync({ tenantId: "t1", name: "New one" });
    });

    expect(client.getQueryState(datasetsQueryKey("t1", 1, ""))?.isInvalidated).toBe(true);
    expect(client.getQueryState(datasetsQueryKey("t1", 2, "x"))?.isInvalidated).toBe(true);
    expect(client.getQueryState(datasetsQueryKey("t2", 1, ""))?.isInvalidated).toBe(false);
    const post = calls.find((c) => c.method?.toUpperCase() === "POST");
    expect(JSON.parse(String(post?.data))).toEqual({ tenant_id: "t1", name: "New one" });
  });

  it("does not retry a failed create", async () => {
    const client = makeClient();
    const { result } = renderHook(() => useCreateDatasetRequest(), { wrapper: wrapperFor(client) });
    http.defaults.adapter = (config) => {
      calls.push(config);
      const response = { data: { code: 409, message: "taken", data: { reason: "duplicate_name" } }, status: 409, statusText: "409", headers: new AxiosHeaders(), config } as never;
      return Promise.reject(new AxiosError("status 409", "ERR_BAD_RESPONSE", config, null, response));
    };
    await act(async () => {
      await expect(result.current.mutateAsync({ tenantId: "t1", name: "Dup" })).rejects.toBeInstanceOf(Error);
    });
    expect(calls.filter((c) => c.method?.toUpperCase() === "POST")).toHaveLength(1);
  });
});
