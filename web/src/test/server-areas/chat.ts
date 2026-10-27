import type { AreaHandler, DatasetServer } from "../dataset-server";
import { UPDATED } from "../dataset-server";
import { assistantStateOf } from "./assistants";

export interface SessionRow { id: string; chat_id: string; name: string; create_time: number; update_time: number; created_by: string }
export interface MessageRow {
  id: string; role: "user" | "assistant"; content: string; created_at: number; finish?: string;
  reference?: { chunks: Record<string, unknown>[]; doc_aggs: Record<string, unknown>[] };
  feedback?: "up" | "down" | null; usage?: { input: number; output: number; total: number; estimated: boolean }; latency_ms?: number; empty?: boolean;
}
interface State { sessions: SessionRow[]; messages: Record<string, MessageRow[]>; next: number }
export const chatStateOf = (server: DatasetServer): State => server.areaState("chat", () => ({ sessions: [], messages: {}, next: 1 }));
export const sessionRow = (n = 1, over: Partial<SessionRow> = {}): SessionRow => ({ id: (n + 1000).toString(16).padStart(32, "0"), chat_id: "1".padStart(32, "0"), name: `Chat ${n}`, create_time: UPDATED, update_time: UPDATED, created_by: "u1", ...over });
export const messageRow = (n = 1, over: Partial<MessageRow> = {}): MessageRow => ({
  id: (n + 2000).toString(16).padStart(32, "0"), role: "assistant", content: `Answer ${n}`, created_at: UPDATED + n,
  finish: "complete", reference: { chunks: [], doc_aggs: [] }, feedback: null, usage: { input: 8, output: 2, total: 10, estimated: false }, latency_ms: 120, empty: false, ...over,
});
export function setSessions(server: DatasetServer, sessions: SessionRow[]): void { Object.assign(chatStateOf(server), { sessions, next: sessions.length + 1 }); }
export function setMessages(server: DatasetServer, sessionId: string, messages: MessageRow[]): void { chatStateOf(server).messages[sessionId] = messages; }
const view = ({ created_by: _user, ...row }: SessionRow) => row;
export const handle: AreaHandler = ({ server, method, url, params, config, ok, failure }) => {
  const route = /^\/api\/v1\/chats\/([^/]+)\/sessions(?:\/([^/]+))?(?:\/messages\/([^/]+)\/feedback)?$/.exec(url);
  if (!route) return undefined;
  const [, chatId, sessionId, messageId] = route.map((part) => part && decodeURIComponent(part));
  const assistant = assistantStateOf(server).rows.find((a) => a.id === chatId && (a.permission === "team" || a.created_by === server.uploader));
  if (!assistant) return failure({ status: 404, message: "not found", reason: "not_found" });
  const state = chatStateOf(server);
  const rows = state.sessions.filter((s) => s.chat_id === chatId && s.created_by === server.uploader);
  if (!sessionId && method === "GET") {
    const page = Math.max(1, Number(params.page) || 1), size = Math.max(1, Number(params.page_size) || 20);
    return ok({ items: rows.slice((page - 1) * size, page * size).map(view), total: rows.length });
  }
  if (!sessionId && method === "POST") {
    const body = JSON.parse(String(config.data ?? "{}")) as { name?: string };
    const row = sessionRow(state.next++, { chat_id: chatId!, name: body.name ?? "", created_by: server.uploader });
    state.sessions.push(row); return ok({ ...view(row), messages: [], has_earlier: false });
  }
  const session = rows.find((s) => s.id === sessionId);
  if (!session) return failure({ status: 404, message: "not found", reason: "not_found" });
  if (method === "GET" && !messageId) {
    const messages = state.messages[session.id] ?? [];
    const end = params.before ? messages.findIndex((m) => m.id === params.before) : messages.length;
    if (end < 0) return failure({ status: 400, message: "bad cursor", reason: "fields_invalid" });
    const size = Math.max(1, Math.min(200, Number(params.limit) || 50)), start = Math.max(0, end - size);
    return ok({ ...view(session), messages: messages.slice(start, end), has_earlier: start > 0 });
  }
  if (method === "DELETE" && !messageId) {
    state.sessions = state.sessions.filter((s) => s !== session); delete state.messages[session.id]; return ok({ deleted: session.id });
  }
  if (method === "POST" && messageId) {
    const row = state.messages[session.id]?.find((m) => m.id === messageId && m.role === "assistant");
    if (!row) return failure({ status: 404, message: "not found", reason: "not_found" });
    const { thumb } = JSON.parse(String(config.data ?? "{}")) as { thumb: unknown };
    if (thumb !== null && thumb !== "up" && thumb !== "down") return failure({ status: 400, message: "bad thumb", reason: "fields_invalid" });
    row.feedback = thumb; return ok({ message_id: row.id, feedback: thumb });
  }
  return undefined;
};

interface StreamOptions { hold?: boolean; holdAfter?: number; errorFrame?: unknown; status?: number; reason?: string }
/** Scripted peer for fetch tests. `release()` sends the held remainder and DONE; no timers. */
export function streamOf(frames: unknown[], options: StreamOptions = {}) {
  let release = () => {};
  const calls: { input: RequestInfo | URL; init?: RequestInit }[] = [];
  const fetcher = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    calls.push({ input, init });
    if (options.status && options.status >= 400) return new Response(JSON.stringify({ code: options.status, message: "refused", data: { reason: options.reason ?? "fields_invalid" } }), { status: options.status, headers: { "content-type": "application/json" } });
    const encoder = new TextEncoder();
    let ended = false;
    const data = [...frames, ...(options.errorFrame ? [options.errorFrame] : [])];
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        const emit = (value: unknown) => controller.enqueue(encoder.encode(`data: ${JSON.stringify(value)}\n\n`));
        const at = options.holdAfter ?? (options.hold ? data.length : null);
        const finish = () => {
          if (ended) return;
          data.slice(at ?? data.length).forEach(emit);
          controller.enqueue(encoder.encode("data: [DONE]\n\n")); controller.close(); ended = true;
        };
        data.slice(0, at ?? data.length).forEach(emit);
        release = finish;
        if (at === null) finish();
      },
      cancel() { ended = true; },
    });
    return new Response(body, { headers: { "content-type": "text/event-stream" } });
  };
  return Object.assign(fetcher, { release: () => release(), calls });
}
