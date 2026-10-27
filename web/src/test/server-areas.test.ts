import { describe, expect, it } from "vitest";
import { createDatasetServer, DATASET_ID, datasetRow } from "./dataset-server";
import { assistantRow, setAssistants, setMembersWithChats } from "./server-areas/assistants";
import { messageRow, sessionRow, setMessages, setSessions } from "./server-areas/chat";
import { setHits } from "./server-areas/retrieval";

const call = (server: ReturnType<typeof createDatasetServer>, method: string, url: string, data?: unknown) =>
  server.adapter({ method, url, data, headers: {} } as never) as Promise<{ data: { code: number; data: unknown } }>;

describe("test server area handlers (R-167)", () => {
  it("answers 404 when nothing matches", async () => {
    const server = createDatasetServer();
    await expect(call(server, "GET", "/nope")).rejects.toMatchObject({ response: { status: 404 } });
  });

  it("runs area handlers before core routes, in order, first answer wins", async () => {
    const server = createDatasetServer();
    server.use(({ method, url, ok }) => (url === "/x" ? ok({ from: "a", method }) : undefined));
    server.use(({ url, ok }) => (url === "/x" || url === "/api/v1/models" ? ok({ from: "b" }) : undefined));
    expect((await call(server, "GET", "/x")).data.data).toEqual({ from: "a", method: "GET" });
    expect((await call(server, "GET", "/api/v1/models")).data.data).toEqual({ from: "b" });
  });

  it("lets a forced failure win over an area", async () => {
    const server = createDatasetServer();
    server.use(({ ok }) => ok("area"));
    server.forced["GET /x"] = { status: 500, message: "boom" };
    await expect(call(server, "GET", "/x")).rejects.toMatchObject({ response: { status: 500 } });
  });

  it("keeps a held request held before an area answers", async () => {
    const server = createDatasetServer();
    server.use(({ ok }) => ok("area"));
    let release: () => void = () => {};
    server.holds["GET /x"] = new Promise<void>((r) => (release = r));
    let done = false;
    const p = call(server, "GET", "/x").then(() => (done = true));
    await Promise.resolve();
    expect(done).toBe(false);
    release();
    await p;
    expect(done).toBe(true);
  });

  it("passes params, parsed method and a POST body to handlers and supports failure()", async () => {
    const server = createDatasetServer();
    server.use(({ method, url, config, failure, ok }) => {
      if (url !== "/p") return undefined;
      if (method !== "POST") return failure({ status: 405, message: "no" });
      return ok(JSON.parse(String(config.data)));
    });
    expect((await call(server, "POST", "/p", JSON.stringify({ a: 1 }))).data.data).toEqual({ a: 1 });
    await expect(call(server, "GET", "/p")).rejects.toMatchObject({ response: { status: 405 } });
  });

  it("isolates area state per server and clears it on reset, keeping handlers", async () => {
    const a = createDatasetServer();
    const b = createDatasetServer();
    a.areaState("k", () => ({ n: 0 })).n = 5;
    expect(b.areaState("k", () => ({ n: 0 })).n).toBe(0);
    expect(a.areaState("k", () => ({ n: 0 })).n).toBe(5);
    a.use(({ ok }) => ok("still"));
    a.reset();
    expect(a.areaState("k", () => ({ n: 0 })).n).toBe(0);
    expect((await call(a, "GET", "/y")).data.data).toBe("still");
  });

  it("still serves core routes when no area answers", async () => {
    const server = createDatasetServer();
    server.datasets[DATASET_ID] = datasetRow();
    server.use(() => undefined);
    const res = await call(server, "GET", `/api/v1/datasets/${DATASET_ID}`);
    expect(res.data.code).toBe(0);
  });
});

describe("Phase 5 server areas", () => {
  it("lists team assistants and only the caller's private assistants without icons", async () => {
    const server = createDatasetServer();
    setAssistants(server, [assistantRow(1), assistantRow(2, { created_by: "other", permission: "me" }), assistantRow(3, { created_by: "other", permission: "team" })]);
    const result = (await call(server, "GET", "/api/v1/chats")).data.data as { items: Record<string, unknown>[] };
    expect(result.items.map((r) => r.id)).toEqual([assistantRow(1).id, assistantRow(3).id]);
    expect(result.items.every((r) => !("icon" in r))).toBe(true);
    await expect(call(server, "GET", `/api/v1/chats/${assistantRow(2).id}`)).rejects.toMatchObject({ response: { status: 404 } });
  });
  it("refuses duplicate names and narrowing with member chats", async () => {
    const server = createDatasetServer(), row = assistantRow(1, { permission: "team" }); setAssistants(server, [row]);
    await expect(call(server, "POST", "/api/v1/chats", JSON.stringify({ name: row.name }))).rejects.toMatchObject({ response: { data: { data: { reason: "duplicate_name" } } } });
    setMembersWithChats(server, row.id, 2);
    await expect(call(server, "PUT", `/api/v1/chats/${row.id}`, JSON.stringify({ permission: "me" }))).rejects.toMatchObject({ response: { data: { data: { reason: "assistant_has_member_chats", count: 2 } } } });
  });
  it("rejects private datasets on a team assistant and keeps hidden bindings on save", async () => {
    const server = createDatasetServer(), row = assistantRow(1, { kb_ids: [DATASET_ID], permission: "me" });
    server.datasets[DATASET_ID] = datasetRow({ permission: "me", created_by: "u1" }); setAssistants(server, [row]);
    await expect(call(server, "PUT", `/api/v1/chats/${row.id}`, JSON.stringify({ permission: "team" }))).rejects.toMatchObject({ response: { data: { data: { reason: "assistant_dataset_not_shared", dataset_ids: [DATASET_ID] } } } });
    server.datasets[DATASET_ID]!.created_by = "other";
    const result = (await call(server, "PUT", `/api/v1/chats/${row.id}`, JSON.stringify({ name: "edited", kb_ids: [] }))).data.data as Record<string, unknown>;
    expect(result).toMatchObject({ kb_ids: [], unavailable_datasets: 1 });
  });
  it("pages messages before a cursor and preserves a sparse reference", async () => {
    const server = createDatasetServer(), chat = assistantRow(1), session = sessionRow(1, { chat_id: chat.id });
    setAssistants(server, [chat]); setSessions(server, [session]);
    setMessages(server, session.id, Array.from({ length: 55 }, (_, i) => messageRow(i + 1, { reference: { chunks: [{ index: 3, unavailable: true }], doc_aggs: [] } })));
    const first = (await call(server, "GET", `/api/v1/chats/${chat.id}/sessions/${session.id}`)).data.data as { messages: Record<string, unknown>[]; has_earlier: boolean };
    expect(first.messages).toHaveLength(50); expect(first.has_earlier).toBe(true); expect(first.messages[0]?.reference).toMatchObject({ chunks: [{ index: 3 }] });
    const second = await server.adapter({ method: "GET", url: `/api/v1/chats/${chat.id}/sessions/${session.id}`, params: { before: first.messages[0]?.id }, headers: {} } as never) as { data: { data: { messages: unknown[] } } };
    expect(second.data.data.messages).toHaveLength(5);
  });
  it("scores and reranks seeded retrieval hits", async () => {
    const server = createDatasetServer(); server.datasets[DATASET_ID] = datasetRow();
    setHits(server, [{ chunk_id: "one", dataset_id: DATASET_ID, content: "reactor coolant", vector_similarity: 0.5 }, { chunk_id: "two", dataset_id: DATASET_ID, content: "unrelated", vector_similarity: 1 }]);
    const result = (await call(server, "POST", "/api/v1/datasets/search", JSON.stringify({ dataset_ids: [DATASET_ID], question: "reactor", similarity_threshold: 0, vector_similarity_weight: 0, rerank_id: "r" }))).data.data as { rerank_applied: boolean; chunks: Record<string, unknown>[] };
    expect(result.rerank_applied).toBe(true); expect(result.chunks[0]).toMatchObject({ chunk_id: "one", rerank_similarity: 1 });
  });
  it("applies forced failures to each area and resets its state", async () => {
    const server = createDatasetServer(), chat = assistantRow(1); setAssistants(server, [chat]);
    for (const route of ["GET /api/v1/chats", `GET /api/v1/chats/${chat.id}/sessions`, "POST /api/v1/datasets/search"]) {
      server.forced[route] = { status: 503, message: "forced" }; const [method, url] = route.split(" ");
      await expect(call(server, method!, url!)).rejects.toMatchObject({ response: { status: 503 } });
    }
    server.reset(); expect((await call(server, "GET", "/api/v1/chats")).data.data).toMatchObject({ items: [], total: 0 });
  });
});
