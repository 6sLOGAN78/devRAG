import { asRecord, text } from "./mapping";

export interface Frame {
  code: number;
  message: string;
  data: {
    answer: string; session_id: string; message_id: string; final: boolean;
    reference: unknown; usage: unknown; latency_ms: number | null; finish: string;
    empty: boolean; notice: unknown; reason: string;
  };
}

function finiteTree(value: unknown): unknown {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (Array.isArray(value)) return value.map(finiteTree);
  if (value !== null && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, finiteTree(item)]));
  return value;
}

export function decodeFrame(raw: unknown): Frame | null {
  const envelope = asRecord(raw);
  if (typeof envelope.code !== "number" || !Number.isFinite(envelope.code)) return null;
  const data = asRecord(finiteTree(envelope.data));
  return {
    code: envelope.code, message: text(envelope.message),
    data: {
      answer: text(data.answer), session_id: text(data.session_id), message_id: text(data.message_id), final: data.final === true,
      reference: data.reference ?? null, usage: data.usage ?? null,
      latency_ms: typeof data.latency_ms === "number" ? data.latency_ms : null,
      finish: text(data.finish), empty: data.empty === true, notice: data.notice ?? null, reason: text(data.reason),
    },
  };
}

export interface TurnState {
  status: "idle" | "streaming" | "finished" | "stopped" | "failed";
  text: string; sessionId: string; messageId: string;
  reference: unknown; usage: unknown; latencyMs: number | null;
  finish: string; empty: boolean; notice: unknown; reason: string;
}
export const initialTurn: TurnState = {
  status: "idle", text: "", sessionId: "", messageId: "", reference: null, usage: null,
  latencyMs: null, finish: "", empty: false, notice: null, reason: "",
};
export type TurnEvent = { type: "start"; sessionId?: string } | { type: "frame"; frame: Frame } | { type: "abort" } | { type: "error"; error: unknown } | { type: "reset" };

export function chatTurnReducer(state: TurnState, event: TurnEvent): TurnState {
  if (event.type === "reset") return initialTurn;
  if (event.type === "start") return { ...initialTurn, status: "streaming", sessionId: event.sessionId ?? "" };
  if (state.status !== "streaming") return state;
  if (event.type === "abort") return { ...state, status: "stopped", finish: "stopped" };
  if (event.type === "error") {
    const error = asRecord(event.error);
    return { ...state, status: "failed", finish: "failed", reason: text(asRecord(error.data).reason) || text(error.kind) || "stream_failed" };
  }
  const { code, data } = event.frame;
  const ids = { sessionId: data.session_id || state.sessionId, messageId: data.message_id || state.messageId };
  if (code !== 0) return { ...state, ...ids, status: "failed", finish: "failed", reason: data.reason || "stream_failed" };
  if (!data.final) return { ...state, ...ids, text: state.text + data.answer };
  return {
    ...state, ...ids, status: "finished", text: data.answer, reference: data.reference, usage: data.usage,
    latencyMs: data.latency_ms, finish: data.finish || "complete", empty: data.empty, notice: data.notice,
  };
}
