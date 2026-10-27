import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { http, registerQueryClient } from "@/services/http";
import { useUserStore } from "@/stores/user-store";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { createDatasetServer } from "@/test/dataset-server";
import { assistantRow, setAssistants } from "@/test/server-areas/assistants";
import { messageRow, sessionRow, setMessages, setSessions, streamOf } from "@/test/server-areas/chat";
import { waitUntil } from "@/test/wait-until";
import { getAuthorization, setAuthorization, removeAuthorization } from "@/utils/authorization";
import { assistantKey, assistantsKey, chatRoot, sessionKey, sessionsKey, useAssistantsRequest, useAssistantRequest, useChatTurn, useSessionRequest, useSessionsRequest, useUpdateAssistant } from "./use-chat-request";
import { useRetrievalSearch } from "./use-retrieval-request";
import { useModelsRequest } from "./use-llm-request";

const server = createDatasetServer(), originalAdapter = http.defaults.adapter;
const A = assistantRow().id, S = sessionRow().id;
let client: QueryClient;
const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
beforeEach(() => {
  server.reset(); http.defaults.adapter = server.adapter;
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }); registerQueryClient(client);
  useWorkspaceStore.getState().reset();
  useUserStore.getState().setUser({ id: "u1", nickname: "Ada", email: "ada@example.test", avatar: "", language: "English", colorSchema: "Bright", tenantId: "t1", tenantName: "Workspace", role: "owner", isSuperuser: false });
  setAuthorization("test-token"); setAssistants(server, [assistantRow()]); setSessions(server, [sessionRow()]);
});
afterEach(() => { cleanup(); client.clear(); http.defaults.adapter = originalAdapter; useUserStore.getState().reset(); useWorkspaceStore.getState().reset(); removeAuthorization(); vi.unstubAllGlobals(); });
const frame = (data: object, code = 0) => ({ code, message: "", data: { session_id: S, message_id: "3".repeat(32), ...data } });

describe("chat query keys and gating", () => {
  it("puts every key below the workspace chat root", () => {
    expect(chatRoot("t1")).toEqual(["ws", "t1", "chat"]);
    for (const key of [assistantsKey("t1", 1, ""), assistantKey("t1", A), sessionsKey("t1", A, 1), sessionKey("t1", A, S)]) expect(key.slice(0, 3)).toEqual(chatRoot("t1"));
  });
  it("does not request chat data before the user/workspace is known", async () => {
    useUserStore.getState().reset(); const { result } = renderHook(() => useAssistantsRequest(), { wrapper });
    expect(result.current.fetchStatus).toBe("idle"); expect(server.callsTo("GET", "/api/v1/chats")).toHaveLength(0);
  });
  it("does not request malformed resource ids", () => {
    const { result } = renderHook(() => ({ assistant: useAssistantRequest("bad"), sessions: useSessionsRequest("bad"), session: useSessionRequest(A, "bad") }), { wrapper });
    expect(Object.values(result.current).every((q) => q.fetchStatus === "idle")).toBe(true);
  });
  it("keeps the old assistant page while the next page is held", async () => {
    setAssistants(server, Array.from({ length: 21 }, (_, i) => assistantRow(i + 1)));
    const { result, rerender } = renderHook(({ page }) => useAssistantsRequest(page), { wrapper, initialProps: { page: 1 } });
    await waitUntil(() => result.current.isSuccess); const old = result.current.data;
    let release = () => {}; server.holds["GET /api/v1/chats"] = new Promise<void>((r) => { release = r; });
    rerender({ page: 2 }); await waitUntil(() => result.current.isPlaceholderData); expect(result.current.data).toBe(old);
    await act(async () => release()); await waitUntil(() => !result.current.isPlaceholderData && result.current.isSuccess);
    expect(result.current.data?.items).toHaveLength(1);
  });
  it("does not carry placeholder assistants across a workspace switch", async () => {
    const { result } = renderHook(() => useAssistantsRequest(), { wrapper }); await waitUntil(() => result.current.isSuccess);
    let release = () => {}; server.holds["GET /api/v1/chats"] = new Promise<void>((r) => { release = r; });
    act(() => { useUserStore.getState().setUser({ ...useUserStore.getState().user!, tenantId: "t2" }); });
    await waitUntil(() => result.current.fetchStatus === "fetching"); expect(result.current.data).toBeUndefined();
    await act(async () => release()); await waitUntil(() => result.current.isSuccess); expect(result.current.data?.items).toEqual([]);
  });
  it("invalidates the workspace root even when a mutation fails", async () => {
    const key = assistantKey("t1", A), other = assistantKey("other", A); client.setQueryData(key, {}); client.setQueryData(other, {});
    server.forced[`PUT /api/v1/chats/${A}`] = { status: 500, message: "failure" };
    const { result } = renderHook(() => useUpdateAssistant(), { wrapper });
    await act(async () => { await expect(result.current.mutateAsync({ chatId: A, changes: { name: "new" } })).rejects.toMatchObject({ status: 500 }); });
    expect(client.getQueryState(key)?.isInvalidated).toBe(true); expect(client.getQueryState(other)?.isInvalidated).toBe(false);
  });
});

describe("retrieval and rerank hooks", () => {
  it("requests the rerank model type", async () => {
    const { result } = renderHook(() => useModelsRequest("rerank"), { wrapper }); await waitUntil(() => result.current.isSuccess);
    expect(server.callsTo("GET", "/api/v1/models")[0]?.params).toEqual({ tenant_id: "t1", type: "rerank" });
  });
  it("does not retry a failed retrieval run", async () => {
    server.forced["POST /api/v1/datasets/search"] = { status: 502, message: "unavailable", reason: "embedding_unavailable" };
    const { result } = renderHook(() => useRetrievalSearch(), { wrapper });
    await act(async () => { await expect(result.current.mutateAsync({ datasetId: A, question: "q" })).rejects.toMatchObject({ status: 502 }); });
    expect(server.callsTo("POST", "/api/v1/datasets/search")).toHaveLength(1);
  });
  it("refuses retrieval before a workspace is known", async () => {
    useUserStore.getState().reset(); const { result } = renderHook(() => useRetrievalSearch(), { wrapper });
    await act(async () => { await expect(result.current.mutateAsync({ datasetId: A, question: "q" })).rejects.toMatchObject({ data: { reason: "workspace_unknown" } }); });
    expect(server.callsTo("POST", "/api/v1/datasets/search")).toHaveLength(0);
  });
});

describe("streaming chat hook", () => {
  it("posts the workspace and replaces deltas with final text", async () => {
    const peer = streamOf([frame({ answer: "partial", final: false }), frame({ answer: "canonical", final: true, finish: "complete" })]); vi.stubGlobal("fetch", peer);
    const { result } = renderHook(() => useChatTurn({ chatId: A }), { wrapper });
    await act(async () => result.current.send("question"));
    expect(result.current.state).toMatchObject({ status: "finished", text: "canonical", sessionId: S });
    expect(JSON.parse(String(peer.calls[0]?.init?.body))).toEqual({ chat_id: A, message: "question", stream: true, tenant_id: "t1" });
  });
  it("stops a held turn, keeps partial text and refetches the saved session", async () => {
    setMessages(server, S, [messageRow(1, { content: "saved partial", finish: "stopped" })]);
    const peer = streamOf([frame({ answer: "partial" })], { hold: true }); vi.stubGlobal("fetch", peer);
    const { result } = renderHook(() => ({ turn: useChatTurn({ chatId: A, sessionId: S }), session: useSessionRequest(A, S) }), { wrapper });
    await waitUntil(() => result.current.session.isSuccess); const before = server.callsTo("GET", `/api/v1/chats/${A}/sessions/${S}`).length;
    let pending: Promise<void>; act(() => { pending = result.current.turn.send("q"); });
    await waitUntil(() => result.current.turn.state.text === "partial");
    await act(async () => { result.current.turn.stop(); await pending; });
    expect(result.current.turn.state.status).toBe("stopped"); await waitUntil(() => server.callsTo("GET", `/api/v1/chats/${A}/sessions/${S}`).length > before);
    expect(result.current.session.data?.messages[0]?.content).toBe("saved partial");
  });
  it("keeps partial text on an error frame", async () => {
    vi.stubGlobal("fetch", streamOf([frame({ answer: "partial" }), frame({ final: true, reason: "rerank_unavailable" }, 502)]));
    const { result } = renderHook(() => useChatTurn({ chatId: A }), { wrapper }); await act(async () => result.current.send("q"));
    expect(result.current.state).toMatchObject({ status: "failed", text: "partial", reason: "rerank_unavailable" });
  });
  it("throws a pre-stream refusal and restores idle state", async () => {
    vi.stubGlobal("fetch", streamOf([], { status: 409, reason: "turn_busy" }));
    const { result } = renderHook(() => useChatTurn({ chatId: A }), { wrapper });
    await act(async () => { await expect(result.current.send("q")).rejects.toMatchObject({ status: 409, data: { reason: "turn_busy" } }); });
    expect(result.current.state.status).toBe("idle");
  });
  it("purges the current token on 401", async () => {
    vi.stubGlobal("fetch", streamOf([], { status: 401 })); const { result } = renderHook(() => useChatTurn({ chatId: A }), { wrapper });
    await act(async () => { await expect(result.current.send("q")).rejects.toMatchObject({ status: 401 }); }); expect(getAuthorization()).toBeNull();
  });
  it("ignores a second send before the held first one settles", async () => {
    const peer = streamOf([frame({ answer: "first" })], { hold: true }); vi.stubGlobal("fetch", peer);
    const { result } = renderHook(() => useChatTurn({ chatId: A }), { wrapper });
    let first: Promise<void>; act(() => { first = result.current.send("first"); }); await waitUntil(() => result.current.state.text === "first");
    await act(async () => result.current.send("second")); expect(peer.calls).toHaveLength(1); await act(async () => { result.current.stop(); await first; });
  });
  it("aborts on unmount and invalidates the chat root", async () => {
    const peer = streamOf([frame({ answer: "partial" })], { hold: true }); vi.stubGlobal("fetch", peer);
    const invalidate = vi.spyOn(client, "invalidateQueries"); const { result, unmount } = renderHook(() => useChatTurn({ chatId: A }), { wrapper });
    let pending: Promise<void>; act(() => { pending = result.current.send("q"); }); await waitUntil(() => result.current.state.text === "partial");
    unmount(); await act(async () => pending); expect(peer.calls[0]?.init?.signal?.aborted).toBe(true);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: chatRoot("t1") });
  });
  it("does not abort a draft turn when its first frame supplies the URL session id", async () => {
    const peer = streamOf([frame({ answer: "partial" }), frame({ answer: "full", final: true })], { holdAfter: 1 }); vi.stubGlobal("fetch", peer);
    const { result, rerender } = renderHook(({ sessionId }: { sessionId?: string }) => useChatTurn({ chatId: A, sessionId }), { wrapper, initialProps: {} });
    let pending: Promise<void>; act(() => { pending = result.current.send("q"); }); await waitUntil(() => result.current.state.sessionId === S); rerender({ sessionId: S });
    await act(async () => { peer.release(); await pending; }); expect(result.current.state).toMatchObject({ status: "finished", text: "full" });
  });
  it("aborts and clears the old turn when the reader selects another session", async () => {
    const peer = streamOf([frame({ answer: "old session" })], { hold: true }); vi.stubGlobal("fetch", peer);
    const { result, rerender } = renderHook(({ sessionId }) => useChatTurn({ chatId: A, sessionId }), { wrapper, initialProps: { sessionId: S } });
    let pending: Promise<void>; act(() => { pending = result.current.send("q"); }); await waitUntil(() => result.current.state.text === "old session");
    rerender({ sessionId: "f".repeat(32) }); await act(async () => pending);
    expect(peer.calls[0]?.init?.signal?.aborted).toBe(true); expect(result.current.state).toMatchObject({ status: "idle", text: "" });
  });
});
