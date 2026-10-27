import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setAuthorization, removeAuthorization } from "@/utils/authorization";
import { waitUntil } from "@/test/wait-until";
import { purgeSession } from "./http";
import { postEventStream } from "./sse";

vi.mock("./http", async () => ({ ...await vi.importActual<typeof import("./http")>("./http"), purgeSession: vi.fn() }));
const encoder = new TextEncoder();
const done = "data: [DONE]\n\n";
let fetchMock = vi.fn();
let cancel = vi.fn();
function reply(chunks: string[], close = true, headers = { "content-type": "text/event-stream" }) {
  return new Response(new ReadableStream({ start(c) { chunks.forEach((s) => c.enqueue(encoder.encode(s))); if (close) c.close(); }, cancel }), { headers });
}
function run(extra = {}) { return postEventStream({ url: "/api/v1/chat/completions", body: { tenant_id: "t" }, onFrame: vi.fn(), ...extra }); }

beforeEach(() => { fetchMock = vi.fn(); cancel = vi.fn(); vi.stubGlobal("fetch", fetchMock); setAuthorization("current"); vi.mocked(purgeSession).mockClear(); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); removeAuthorization(); });

describe("authenticated POST event stream", () => {
  it("posts JSON with the current token in a header and credentials", async () => {
    fetchMock.mockResolvedValue(reply([done])); await run();
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/chat/completions", expect.objectContaining({ method: "POST", credentials: "same-origin", body: '{"tenant_id":"t"}', headers: expect.objectContaining({ Authorization: "Bearer current", Accept: "text/event-stream" }) }));
  });
  it("handles a frame split anywhere", async () => {
    const onFrame = vi.fn(); fetchMock.mockResolvedValue(reply(["da", 'ta: {"a":', "1}\n", "\n", done]));
    await expect(run({ onFrame })).resolves.toBe("done"); expect(onFrame).toHaveBeenCalledWith({ a: 1 });
  });
  it("decodes UTF-8 characters split across individual byte chunks", async () => {
    const onFrame = vi.fn();
    const bytes = encoder.encode('data: {"answer":"你好"}\n\n' + done);
    fetchMock.mockResolvedValue(new Response(new ReadableStream({ start(c) { for (const byte of bytes) c.enqueue(Uint8Array.of(byte)); c.close(); } }), { headers: { "content-type": "text/event-stream" } }));
    await run({ onFrame }); expect(onFrame).toHaveBeenCalledWith({ answer: "你好" });
  });
  it("handles CRLF split between chunks", async () => {
    const onFrame = vi.fn(); fetchMock.mockResolvedValue(reply(['data: {"a":1}\r', "\n\r", "\n", done]));
    await run({ onFrame }); expect(onFrame).toHaveBeenCalledTimes(1);
  });
  it("ignores comment frames", async () => {
    const onFrame = vi.fn(); fetchMock.mockResolvedValue(reply([": ping\n\n", done])); await run({ onFrame }); expect(onFrame).not.toHaveBeenCalled();
  });
  it("joins multi-line event data", async () => {
    const onFrame = vi.fn(); fetchMock.mockResolvedValue(reply(['data: {"a":\ndata: 2}\n\n', done])); await run({ onFrame }); expect(onFrame).toHaveBeenCalledWith({ a: 2 });
  });
  it("reads multiple events from one chunk", async () => {
    const onFrame = vi.fn(); fetchMock.mockResolvedValue(reply(["data: 1\n\ndata: 2\n\n" + done])); await run({ onFrame }); expect(onFrame.mock.calls).toEqual([[1], [2]]);
  });
  it("bounds incomplete frames without limiting the total stream size", async () => {
    const onFrame = vi.fn(); fetchMock.mockResolvedValue(reply(["data: 1\n\n".repeat(100) + done]));
    await run({ maxBufferBytes: 32, onFrame }); expect(onFrame).toHaveBeenCalledTimes(100);
  });
  it("stops dispatching after DONE", async () => {
    const onFrame = vi.fn(); fetchMock.mockResolvedValue(reply([done + "data: 2\n\n"])); await run({ onFrame }); expect(onFrame).not.toHaveBeenCalled();
  });
  it("ignores non-JSON event data", async () => {
    const onFrame = vi.fn(); fetchMock.mockResolvedValue(reply(["data: nope\n\n", done])); await run({ onFrame }); expect(onFrame).not.toHaveBeenCalled();
  });
  it("cancels a reader aborted mid-frame", async () => {
    const controller = new AbortController(); fetchMock.mockResolvedValue(reply(['data: {"a":'], false));
    const pending = run({ signal: controller.signal }); await waitUntil(() => fetchMock.mock.calls.length > 0); controller.abort();
    await expect(pending).resolves.toBe("aborted"); expect(cancel).toHaveBeenCalled();
  });
  it("purges a 401 carrying the current token", async () => {
    fetchMock.mockResolvedValue(new Response('{"code":401,"data":null}', { status: 401 })); await expect(run()).rejects.toMatchObject({ status: 401 }); expect(purgeSession).toHaveBeenCalledOnce();
  });
  it("does not purge a stale-token 401", async () => {
    fetchMock.mockImplementation(async () => { setAuthorization("replacement"); return new Response("{}", { status: 401 }); });
    await expect(run()).rejects.toMatchObject({ status: 401 }); expect(purgeSession).not.toHaveBeenCalled();
  });
  it("preserves the 401 even when session purge aborts the owning turn", async () => {
    const controller = new AbortController(); vi.mocked(purgeSession).mockImplementationOnce(() => controller.abort());
    fetchMock.mockResolvedValue(new Response('{"code":401,"data":null}', { status: 401 }));
    await expect(run({ signal: controller.signal })).rejects.toMatchObject({ status: 401 });
  });
  it("preserves the typed JSON reason on a refusal", async () => {
    fetchMock.mockResolvedValue(new Response('{"code":409,"data":{"reason":"turn_busy"}}', { status: 409 })); await expect(run()).rejects.toMatchObject({ status: 409, data: { reason: "turn_busy" } });
  });
  it("refuses the wrong successful content type", async () => {
    fetchMock.mockResolvedValue(reply([done], true, { "content-type": "application/json" })); await expect(run()).rejects.toMatchObject({ kind: "network" });
  });
  it("refuses cross-origin URLs before fetch", async () => {
    await expect(run({ url: "https://attacker.invalid/stream" })).rejects.toMatchObject({ kind: "network" }); expect(fetchMock).not.toHaveBeenCalled();
  });
  it("fails an idle stream with a timeout kind", async () => {
    vi.useFakeTimers(); fetchMock.mockResolvedValue(reply([], false)); const pending = run({ idleMs: 100 });
    const checked = expect(pending).rejects.toMatchObject({ kind: "timeout" }); await vi.advanceTimersByTimeAsync(101); await checked; expect(cancel).toHaveBeenCalled();
  });
  it.each(["data: " + "x".repeat(300), "nonsense".repeat(50)])("bounds huge incomplete lines", async (line) => {
    fetchMock.mockResolvedValue(reply([line], false)); await expect(run({ maxBufferBytes: 128 })).rejects.toMatchObject({ kind: "network" }); expect(cancel).toHaveBeenCalled();
  });
  it("fails a truncated stream without DONE", async () => {
    fetchMock.mockResolvedValue(reply(['data: {"a":1}\n\n'])); await expect(run()).rejects.toMatchObject({ kind: "network" });
  });
});
