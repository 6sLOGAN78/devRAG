/** The production SSE client against Nginx and the app; only the provider's end of the wire is local. */
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { ApiError } from "@/services/http";
import { postEventStream } from "@/services/sse";
import { chatTurnReducer, decodeFrame, initialTurn } from "@/services/chat-turn";
import { saveProvider } from "@/services/model-service";
import { getDocument, parseDocuments, uploadDocument } from "@/services/document-service";
import { call, createAccount, createWorld, destroyWorld, join, resetApp, type World } from "@/test/live/ingest-world";
import { waitUntil } from "@/test/wait-until";
import { getAuthorization, setAuthorization } from "@/utils/authorization";

let world: World;
let chatId = "";
const completion = () => new URL("/api/v1/chat/completions", window.location.origin).href;
const body = (extra = {}) => ({ chat_id: chatId, message: "What temperature does the amber reactor use?", stream: true, ...extra });
interface Session { messages: { role: string; content: string; finish: string }[] }

beforeAll(async () => {
  world = await createWorld("chat", "team");
  setAuthorization(world.owner.session);
  await saveProvider({ tenantId: world.owner.tenantId, provider: "openai-compatible", baseUrl: world.fake.stackBaseUrl,
    models: [{ name: "fake-embed", type: "embedding" }, { name: "fake-chat", type: "chat" }] });
  const file = new File(["The amber reactor uses a coolant temperature of 612 degrees."], "reactor.txt", { type: "text/plain" });
  const doc = await uploadDocument(world.datasetId, file);
  await parseDocuments(world.datasetId, [doc.id], "1");
  await waitUntil(async () => (await getDocument(world.datasetId, doc.id)).run === "3", { describe: "chat document parsed", timeout: 150_000 });
  const made = await call<{ id: string }>("/api/v1/chats", { method: "POST", bearer: world.owner.session,
    body: { name: "Live SSE", permission: "team", kb_ids: [world.datasetId], llm_id: "fake-chat@OpenAI-API-Compatible", similarity_threshold: 0, vector_similarity_weight: 0 } });
  expect(made.status).toBe(200);
  expect(made.envelope?.code).toBe(0);
  chatId = made.envelope!.data.id;
}, 300_000);
afterEach(() => { world.fake.releaseChat(); world.fake.chatMode = "plain"; resetApp(); });
afterAll(async () => { await destroyWorld(world); });

describe("live chat stream", () => {
  it("parses deltas, the canonical cited final frame and DONE through ingress", async () => {
    setAuthorization(world.owner.session);
    world.fake.chatMode = "marker";
    let state = chatTurnReducer(initialTurn, { type: "start" });
    let deltas = 0;
    const result = await postEventStream({ url: completion(), body: body(), onFrame(raw) {
      const frame = decodeFrame(raw);
      expect(frame).not.toBeNull();
      if (frame && !frame.data.final) deltas += 1;
      if (frame) state = chatTurnReducer(state, { type: "frame", frame });
    } });
    expect(result).toBe("done");
    expect(deltas).toBeGreaterThan(0);
    expect(state.status).toBe("finished");
    expect(state.text).toBe("Answer ##0$$ done.");
    expect(state.reference).toMatchObject({ chunks: [expect.objectContaining({ content: expect.stringContaining("612") })] });
  });

  it("stores a stopped partial after abort and releases the session for a following turn", async () => {
    setAuthorization(world.owner.session);
    world.fake.chatMode = "gated";
    const controller = new AbortController();
    let sessionId = "", received = "";
    const result = await postEventStream({ url: completion(), body: body(), signal: controller.signal, onFrame(raw) {
      const frame = decodeFrame(raw);
      if (frame?.data.answer && !frame.data.final) {
        sessionId = frame.data.session_id;
        received += frame.data.answer;
        controller.abort();
      }
    } });
    expect(result).toBe("aborted");
    expect(received.length).toBeGreaterThan(0);
    await waitUntil(async () => {
      const read = await call<Session>(`/api/v1/chats/${chatId}/sessions/${sessionId}`, { bearer: world.owner.session });
      const partial = read.envelope?.data.messages.at(-1);
      return partial?.finish === "stopped" && partial.content.startsWith(received);
    }, { describe: "the app to store the stopped partial", timeout: 30_000 });
    world.fake.releaseChat();
    world.fake.chatMode = "plain";
    expect(await postEventStream({ url: completion(), body: body({ session_id: sessionId }), onFrame() {} })).toBe("done");
  });

  it("preserves the current session on a stale 401 and purges a revoked current token", async () => {
    setAuthorization("expired-live-session");
    const stale = postEventStream({ url: completion(), body: body(), onFrame() {} });
    setAuthorization(world.owner.session);
    await expect(stale).rejects.toMatchObject({ status: 401 });
    expect(getAuthorization()).toBe(world.owner.session);
    const revoked = await createAccount("chat-revoked");
    expect((await call("/api/v1/auth/logout", { method: "POST", bearer: revoked.session })).status).toBe(200);
    setAuthorization(revoked.session);
    await expect(postEventStream({ url: completion(), body: body(), onFrame() {} })).rejects.toMatchObject({ status: 401 });
    expect(getAuthorization()).toBeNull();
  });

  it("exposes a typed pre-stream refusal when a shared dataset becomes private", async () => {
    const member = await createAccount("chat-member");
    await join(world.owner, member);
    const changed = await call(`/api/v1/datasets/${world.datasetId}`, { method: "PUT", bearer: world.owner.session, body: { permission: "me" } });
    expect(changed.status).toBe(200);
    setAuthorization(member.session);
    const failure = await postEventStream({ url: completion(), body: body(), onFrame() {} }).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ status: 409, data: { reason: "datasets_unavailable" } });
  });
});
