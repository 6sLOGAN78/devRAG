import { beforeEach, describe, expect, it, vi } from "vitest";
import { request } from "./http";
import { createAssistant, createSession, deleteAssistant, deleteSession, getAssistant, getSession, listAssistants, listSessions, referenceChunk, setFeedback, toAssistant, toAssistantDetail, toMessage, toReference, updateAssistant } from "./chat-service";

vi.mock("./http", () => ({ request: vi.fn() }));
const send = vi.mocked(request);
beforeEach(() => { send.mockReset(); send.mockResolvedValue({}); });

describe("defensive chat response mappers", () => {
  it("omits list icons and unknown fields", () => {
    const result = toAssistant({ id: "a", name: "<script>x</script>", icon: "data:x", secret: "no" });
    expect(result.name).toBe("<script>x</script>"); expect(result).not.toHaveProperty("icon"); expect(result).not.toHaveProperty("secret");
  });
  it("maps missing detail fields without throwing", () => expect(toAssistantDetail(undefined)).toMatchObject({ id: "", icon: "", kbIds: [], unavailableDatasets: 0 }));
  it("keeps reference indices sparse and finds by each chunk's index", () => {
    const reference = toReference({ chunks: [{ index: 0, content: "first" }, { index: 3, content: "fourth" }], doc_aggs: [] });
    expect(reference.chunks.map((c) => c.index)).toEqual([0, 3]); expect(referenceChunk(reference, 3)).toMatchObject({ content: "fourth" }); expect(referenceChunk(reference, 1)).toBeUndefined();
  });
  it("preserves redacted unavailable chunks without identifiers", () => {
    expect(toReference({ chunks: [{ index: 3, unavailable: true, content: "must not escape" }] }).chunks).toEqual([{ index: 3, unavailable: true }]);
  });
  it.each([NaN, Infinity, "Infinity", "NaN", null, {}])("maps non-finite or missing scores to null: %s", (score) => {
    const reference = toReference({ chunks: [{ index: 0, similarity: score }] });
    expect(referenceChunk(reference, 0)).toMatchObject({ similarity: null });
  });
  it("drops malformed positions, page dimensions and indices", () => {
    const position = { page: 1, x0: 2, x1: 3, top: 4, bottom: 5 };
    const chunk = referenceChunk(toReference({ chunks: [{ index: 2, positions: [position, { ...position, top: "4" }], page_sizes: { "1": [600, 800], "2": [Infinity, 3] } }, { index: -1 }] }), 2);
    expect(chunk).toMatchObject({ positions: [position], pageSizes: { "1": [600, 800] } });
    expect(toReference({ chunks: [{ index: -1 }, {}] }).chunks).toEqual([]);
  });
  it("maps message metadata and defaults an unknown role safely", () => {
    expect(toMessage({ role: "assistant", content: "answer", finish: "stopped", latency_ms: Infinity, feedback: "up", usage: { total: 3 } })).toMatchObject({ role: "assistant", content: "answer", finish: "stopped", latencyMs: null, feedback: "up", usage: { total: 3 } });
    expect(toMessage(undefined).role).toBe("user");
  });
});

describe("chat service request contracts", () => {
  it("lists and opens assistants with silent requests", async () => {
    send.mockResolvedValueOnce({ items: [{ id: "a" }], total: 1 }); expect((await listAssistants("t", 2, "q")).total).toBe(1);
    expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ params: { tenant_id: "t", page: 2, page_size: 20, keywords: "q" } }), { silent: true });
    await getAssistant("a/b"); expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ url: "/api/v1/chats/a%2Fb" }), { silent: true });
  });
  it("creates with a workspace and sends only supplied update keys", async () => {
    await createAssistant("t", { name: "new" }); expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ method: "POST", data: { tenant_id: "t", name: "new" } }), { silent: true });
    await updateAssistant("a", { name: "changed", icon: null }); expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ method: "PUT", data: { name: "changed", icon: null } }), { silent: true });
  });
  it("maps nested prompt changes without filling in absent keys", async () => {
    await updateAssistant("a", { promptConfig: { system: "custom" }, rerankId: null });
    expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ data: { prompt_config: { system: "custom" }, rerank_id: null } }), { silent: true });
  });
  it("loads sessions and the before cursor and maps earlier-message state", async () => {
    send.mockResolvedValueOnce({ items: [], total: 0 }); await listSessions("a", 2);
    expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ params: { page: 2, page_size: 20 } }), { silent: true });
    send.mockResolvedValueOnce({ messages: [{ id: "m", role: "user" }], has_earlier: true });
    expect(await getSession("a", "s", "before")).toMatchObject({ hasEarlier: true, messages: [{ id: "m" }] });
    expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ params: { before: "before", limit: 50 } }), { silent: true });
  });
  it("creates and deletes sessions and assistants", async () => {
    await createSession("a", "name"); expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ method: "POST", data: { name: "name" } }), { silent: true });
    await deleteSession("a", "s"); expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ method: "DELETE", url: "/api/v1/chats/a/sessions/s" }), { silent: true });
    await deleteAssistant("a"); expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ method: "DELETE", url: "/api/v1/chats/a" }), { silent: true });
  });
  it("sends the nullable feedback thumb and optional comment", async () => {
    send.mockResolvedValue({ feedback: null }); expect(await setFeedback("a", "s", "m", null)).toBeNull();
    expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ method: "POST", data: { thumb: null }, url: "/api/v1/chats/a/sessions/s/messages/m/feedback" }), { silent: true });
  });
});
