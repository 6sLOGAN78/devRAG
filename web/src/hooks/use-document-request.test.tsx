import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { SessionUser } from "@/interfaces/user";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import {
  documentDetailKey,
  documentsKeyRoot,
  documentsQueryKey,
  useDeleteDocumentsRequest,
  useDocumentDetailRequest,
  useDocumentsRequest,
  useInvalidateOnParseEnd,
  useParseDocumentsRequest,
  usePollHealth,
  useSetDocumentsEnabledRequest,
  useUpdateDocumentSettingsRequest,
} from "./use-document-request";
import { ingestionKeyRoot, ingestionLogKey, ingestionLogsKey, ingestionSummaryKey, useIngestionLogRequest, useIngestionLogsRequest, useIngestionSummaryRequest } from "./use-ingestion-request";
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

let overrides: Record<string, (config: InternalAxiosRequestConfig) => Promise<never>> = {};

const adapter: AxiosAdapter = (config) => {
  calls.push(config);
  const key = `${String(config.method).toUpperCase()} ${config.url}`;
  const override = overrides[key];
  if (override) return override(config);
  if (key === "GET /v1/tenant/list") return Promise.resolve(ok(config, []));
  if (key === "GET /api/v1/datasets/kb1/documents") return Promise.resolve(ok(config, { items: [], total: 0 }));
  if (key === "DELETE /api/v1/datasets/kb1/documents") return Promise.resolve(ok(config, { deleted: 1 }));
  return Promise.reject(new Error(`unexpected ${key}`));
};

let client: QueryClient;
const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;

beforeEach(() => {
  calls = [];
  overrides = {};
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

const running = { id: "d1", name: "a.pdf", run: "1" };
const idle = { id: "d1", name: "a.pdf", run: "3" };
const page = (items: unknown[]) => ({ items, total: items.length });

/** The refetch interval the mounted observer of `key` would use now. */
function intervalOf(key: readonly unknown[]): number | false | undefined {
  const query = client.getQueryCache().find({ queryKey: key });
  const option = query?.observers[0]?.options.refetchInterval;
  return typeof option === "function" ? (option as (q: unknown) => number | false | undefined)(query) : option;
}

const timeoutError = (config: InternalAxiosRequestConfig) => Promise.reject(new AxiosError("timeout of 30000ms exceeded", "ECONNABORTED", config));

describe("useDocumentsRequest polling (FE-01)", () => {
  it("keeps the previous page while the next one loads", async () => {
    let release: () => void = () => undefined;
    overrides["GET /api/v1/datasets/kb1/documents"] = (config) =>
      config.params?.page === 2
        ? new Promise((resolve) => {
            release = () => resolve(ok(config, page([idle])) as never);
          })
        : Promise.resolve(ok(config, page([{ ...idle, id: "p1" }])) as never);
    const { result, rerender } = renderHook(({ n }) => useDocumentsRequest({ datasetId: "kb1", page: n, keywords: "" }), { wrapper, initialProps: { n: 1 } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    rerender({ n: 2 });
    await waitFor(() => expect(result.current.isFetching).toBe(true));
    expect(result.current.isPlaceholderData).toBe(true);
    expect(result.current.data?.items[0]?.id).toBe("p1");
    await act(async () => release());
    await waitFor(() => expect(result.current.isPlaceholderData).toBe(false));
  });

  it("polls every 2000 ms only while a row is running, and never in the background", async () => {
    let body = page([running]);
    overrides["GET /api/v1/datasets/kb1/documents"] = (config) => Promise.resolve(ok(config, body) as never);
    const { result } = renderHook(() => useDocumentsRequest({ datasetId: "kb1", page: 1, keywords: "" }), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const key = documentsQueryKey("t1", "kb1", 1, "");
    expect(intervalOf(key)).toBe(2000);
    expect(client.getQueryCache().find({ queryKey: key })?.observers[0]?.options.refetchIntervalInBackground).toBe(false);
    body = page([idle]);
    await act(async () => void (await result.current.refetch()));
    expect(intervalOf(key)).toBe(false);
  });
});

describe("usePollHealth", () => {
  it("pauses after three failed polls in a row and recovers on a success", () => {
    const { result, rerender } = renderHook((q: { errorUpdatedAt: number; dataUpdatedAt: number }) => usePollHealth(q), {
      initialProps: { errorUpdatedAt: 0, dataUpdatedAt: 1 },
    });
    expect(result.current.pollPaused).toBe(false);
    rerender({ errorUpdatedAt: 2, dataUpdatedAt: 1 });
    rerender({ errorUpdatedAt: 3, dataUpdatedAt: 1 });
    expect(result.current.pollPaused).toBe(false);
    rerender({ errorUpdatedAt: 4, dataUpdatedAt: 1 });
    expect(result.current.pollPaused).toBe(true);
    rerender({ errorUpdatedAt: 4, dataUpdatedAt: 5 });
    expect(result.current.pollPaused).toBe(false);
  });
});

describe("mutations refresh in onSettled (FE-03)", () => {
  const seed = () => {
    const keys = {
      documents: documentsQueryKey("t1", "kb1", 1, ""),
      summary: ingestionSummaryKey("t1", "kb1"),
      list: [...datasetsKeyRoot("t1"), 1, ""],
      detail: datasetQueryKey("t1", "kb1"),
      other: documentsQueryKey("t1", "kb2", 1, ""),
    };
    for (const key of Object.values(keys)) client.setQueryData(key, { seeded: true });
    return keys;
  };
  const expectRefreshed = (keys: ReturnType<typeof seed>) => {
    expect(client.getQueryState(keys.documents)?.isInvalidated).toBe(true);
    expect(client.getQueryState(keys.summary)?.isInvalidated).toBe(true);
    expect(client.getQueryState(keys.list)?.isInvalidated).toBe(true);
    expect(client.getQueryState(keys.detail)?.isInvalidated).toBe(true);
    expect(client.getQueryState(keys.other)?.isInvalidated).toBe(false);
  };

  it("a parse that timed out on the client still refreshes the list", async () => {
    overrides["POST /api/v1/datasets/kb1/documents/parse"] = timeoutError as never;
    const keys = seed();
    const { result } = renderHook(() => useParseDocumentsRequest(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ datasetId: "kb1", ids: ["d1"], run: "1" }).catch(() => undefined);
    });
    expectRefreshed(keys);
  });

  it("a successful parse refreshes too", async () => {
    overrides["POST /api/v1/datasets/kb1/documents/parse"] = (config) => Promise.resolve(ok(config, { started: ["d1"], cancelled: [] }) as never);
    const keys = seed();
    const { result } = renderHook(() => useParseDocumentsRequest(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ datasetId: "kb1", ids: ["d1"], run: "1" });
    });
    expectRefreshed(keys);
  });

  it("the search switch and the settings refresh after a refusal", async () => {
    overrides["POST /api/v1/datasets/kb1/documents/batch-update-status"] = timeoutError as never;
    overrides["PATCH /api/v1/datasets/kb1/documents/d1"] = timeoutError as never;
    const keys = seed();
    const sw = renderHook(() => useSetDocumentsEnabledRequest(), { wrapper });
    await act(async () => {
      await sw.result.current.mutateAsync({ datasetId: "kb1", ids: ["d1"], enabled: false }).catch(() => undefined);
    });
    expectRefreshed(keys);
    client.clear();
    const keys2 = seed();
    const st = renderHook(() => useUpdateDocumentSettingsRequest(), { wrapper });
    await act(async () => {
      await st.result.current.mutateAsync({ datasetId: "kb1", docId: "d1", changes: { chunkTokenNum: 256 } }).catch(() => undefined);
    });
    expectRefreshed(keys2);
  });
});

describe("detail and ingestion hooks poll while something runs", () => {
  it("the document detail polls while run is 1", async () => {
    overrides["GET /api/v1/datasets/kb1/documents/d1"] = (config) => Promise.resolve(ok(config, { ...running, preview: "none" }) as never);
    const { result } = renderHook(() => useDocumentDetailRequest("kb1", "d1"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(intervalOf(documentDetailKey("t1", "kb1", "d1"))).toBe(2000);
    expect(documentDetailKey("t1", "kb1", "d1").slice(0, 4)).toEqual(documentsKeyRoot("t1", "kb1"));
  });

  it("the summary polls while running > 0 and the log list while a row runs", async () => {
    overrides["GET /api/v1/datasets/kb1/ingestions/summary"] = (config) => Promise.resolve(ok(config, { running: 2 }) as never);
    overrides["GET /api/v1/datasets/kb1/ingestions"] = (config) => Promise.resolve(ok(config, page([{ id: "l1", result: "running" }])) as never);
    overrides["GET /api/v1/datasets/kb1/ingestions/l1"] = (config) => Promise.resolve(ok(config, { id: "l1", result: "running", log: [] }) as never);
    const summary = renderHook(() => useIngestionSummaryRequest("kb1"), { wrapper });
    const logs = renderHook(() => useIngestionLogsRequest("kb1", 1), { wrapper });
    const one = renderHook(() => useIngestionLogRequest("kb1", "l1"), { wrapper });
    await waitFor(() => expect(summary.result.current.isSuccess && logs.result.current.isSuccess && one.result.current.isSuccess).toBe(true));
    expect(intervalOf(ingestionSummaryKey("t1", "kb1"))).toBe(2000);
    expect(intervalOf(ingestionLogsKey("t1", "kb1", 1))).toBe(2000);
    expect(intervalOf(ingestionLogKey("t1", "kb1", "l1"))).toBe(2000);
    expect(ingestionSummaryKey("t1", "kb1").slice(0, 4)).toEqual(ingestionKeyRoot("t1", "kb1"));
  });
});

describe("useInvalidateOnParseEnd", () => {
  it("invalidates the dataset detail and the summary once when a running row stops", () => {
    const detailKey = datasetQueryKey("t1", "kb1");
    const summaryKey = ingestionSummaryKey("t1", "kb1");
    client.setQueryData(detailKey, { seeded: true });
    client.setQueryData(summaryKey, { seeded: true });
    type Row = { id: string; run: string };
    const { rerender } = renderHook(({ items }: { items: Row[] }) => useInvalidateOnParseEnd("kb1", items as never), {
      wrapper,
      initialProps: { items: [{ id: "d1", run: "1" }] },
    });
    expect(client.getQueryState(detailKey)?.isInvalidated).toBe(false);
    rerender({ items: [{ id: "d1", run: "3" }] });
    expect(client.getQueryState(detailKey)?.isInvalidated).toBe(true);
    expect(client.getQueryState(summaryKey)?.isInvalidated).toBe(true);
  });
});
