import { describe, expect, it } from "vitest";
import { chatTurnReducer, decodeFrame, initialTurn } from "./chat-turn";

const start = () => chatTurnReducer(initialTurn, { type: "start" });
const frame = (data: object, code = 0) => decodeFrame({ code, message: "message", data })!;

describe("chat turn reducer", () => {
  it("starts an empty streaming turn", () => expect(start()).toMatchObject({ status: "streaming", text: "" }));
  it("appends deltas and records identifiers", () => {
    const first = chatTurnReducer(start(), { type: "frame", frame: frame({ answer: "a", session_id: "s", message_id: "m" }) });
    expect(chatTurnReducer(first, { type: "frame", frame: frame({ answer: "b" }) })).toMatchObject({ text: "ab", sessionId: "s", messageId: "m" });
  });
  it("replaces incomplete deltas with the canonical final answer", () => {
    const partial = chatTurnReducer(start(), { type: "frame", frame: frame({ answer: "lost" }) });
    expect(chatTurnReducer(partial, { type: "frame", frame: frame({ answer: "canonical", final: true, finish: "complete" }) })).toMatchObject({ status: "finished", text: "canonical" });
  });
  it("attaches final metadata", () => {
    const end = chatTurnReducer(start(), { type: "frame", frame: frame({ final: true, reference: { chunks: [] }, usage: { total: 3 }, latency_ms: 12, empty: true, notice: { unavailable_datasets: 1 } }) });
    expect(end).toMatchObject({ reference: { chunks: [] }, usage: { total: 3 }, latencyMs: 12, empty: true, notice: { unavailable_datasets: 1 } });
  });
  it("keeps partial text when a typed error frame arrives", () => {
    const partial = chatTurnReducer(start(), { type: "frame", frame: frame({ answer: "part" }) });
    expect(chatTurnReducer(partial, { type: "frame", frame: frame({ final: true, reason: "provider_failed" }, 500) })).toMatchObject({ status: "failed", text: "part", reason: "provider_failed" });
  });
  it("marks an abort as stopped", () => expect(chatTurnReducer(start(), { type: "abort" })).toMatchObject({ status: "stopped", finish: "stopped" }));
  it("keeps partial text on a transport error", () => {
    const partial = chatTurnReducer(start(), { type: "frame", frame: frame({ answer: "part" }) });
    expect(chatTurnReducer(partial, { type: "error", error: new Error("disconnected") })).toMatchObject({ status: "failed", text: "part" });
  });
  it("ignores frames after a finished turn", () => {
    const end = chatTurnReducer(start(), { type: "frame", frame: frame({ answer: "done", final: true }) });
    expect(chatTurnReducer(end, { type: "frame", frame: frame({ answer: "extra" }) })).toBe(end);
  });
  it("resets a stopped turn", () => expect(chatTurnReducer(chatTurnReducer(start(), { type: "abort" }), { type: "reset" })).toEqual(initialTurn));
  it("rejects malformed frames", () => {
    for (const raw of [null, [], "x", {}, { code: Infinity }]) expect(decodeFrame(raw)).toBeNull();
  });
  it("turns non-finite nested values into null", () => {
    expect(frame({ latency_ms: Infinity, usage: { total: NaN }, reference: { chunks: [{ similarity: Infinity }] } }).data).toMatchObject({ latency_ms: null, usage: { total: null }, reference: { chunks: [{ similarity: null }] } });
  });
});
