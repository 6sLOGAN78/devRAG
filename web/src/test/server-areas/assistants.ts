import type { AreaHandler, DatasetServer } from "../dataset-server";
import { UPDATED } from "../dataset-server";

export interface AssistantRow {
  id: string; tenant_id: string; name: string; icon: string; permission: "me" | "team"; created_by: string; kb_ids: string[];
  llm_id: string; rerank_id: string; similarity_threshold: number; vector_similarity_weight: number; top_n: number;
  prompt_config: { system: string; prologue: string; empty_response: string }; llm_setting: Record<string, number>; update_time: number;
}
interface State { rows: AssistantRow[]; memberChats: Record<string, number>; next: number }
export const assistantStateOf = (server: DatasetServer): State => server.areaState("assistants", () => ({ rows: [], memberChats: {}, next: 1 }));
export const assistantRow = (n = 1, over: Partial<AssistantRow> = {}): AssistantRow => ({
  id: n.toString(16).padStart(32, "0"), tenant_id: "t1", name: `Assistant ${n}`, icon: "", permission: "me", created_by: "u1", kb_ids: [],
  llm_id: "chat-one@OpenRouter", rerank_id: "", similarity_threshold: 0.2, vector_similarity_weight: 0.3, top_n: 6,
  prompt_config: { system: "Answer from the context.", prologue: "", empty_response: "No matching passages were found." },
  llm_setting: { temperature: 0.2, top_p: 1, max_tokens: 1024, presence_penalty: 0, frequency_penalty: 0 }, update_time: UPDATED, ...over,
});
export function setAssistants(server: DatasetServer, rows: AssistantRow[]): void { Object.assign(assistantStateOf(server), { rows, next: rows.length + 1 }); }
export function setMembersWithChats(server: DatasetServer, chatId: string, count: number): void { assistantStateOf(server).memberChats[chatId] = count; }
const visible = (server: DatasetServer, row: AssistantRow): boolean => row.permission === "team" || row.created_by === server.uploader;
const datasetVisible = (server: DatasetServer, id: string): boolean => {
  const row = server.datasets[id]; return row !== undefined && (row.permission === "team" || row.created_by === server.uploader);
};
function memberCount(server: DatasetServer, row: AssistantRow): number {
  const override = assistantStateOf(server).memberChats[row.id];
  if (override !== undefined) return override;
  const state = server.areaState<{ sessions: { chat_id: string; created_by: string }[]; messages: object; next: number }>("chat", () => ({ sessions: [], messages: {}, next: 1 }));
  return new Set(state.sessions.filter((s) => s.chat_id === row.id && s.created_by !== server.uploader).map((s) => s.created_by)).size;
}
function view(server: DatasetServer, row: AssistantRow, detail: boolean): Record<string, unknown> {
  const { tenant_id: _tenant, icon, ...allowed } = row;
  const ids = row.kb_ids.filter((id) => datasetVisible(server, id));
  return { ...allowed, kb_ids: ids, unavailable_datasets: row.kb_ids.length - ids.length, ...(detail ? { icon, members_with_chats: memberCount(server, row) } : {}) };
}
export const handle: AreaHandler = ({ server, method, url, params, config, ok, failure }) => {
  const route = /^\/api\/v1\/chats(?:\/([^/]+))?$/.exec(url);
  if (!route) return undefined;
  const id = route[1] ? decodeURIComponent(route[1]) : undefined;
  const state = assistantStateOf(server), tenant = String(params.tenant_id ?? "t1");
  if (method === "GET" && id === undefined) {
    const keywords = String(params.keywords ?? "").toLowerCase();
    const rows = state.rows.filter((r) => r.tenant_id === tenant && visible(server, r) && r.name.toLowerCase().includes(keywords));
    const page = Math.max(1, Number(params.page) || 1), size = Math.max(1, Number(params.page_size) || 20);
    return ok({ items: rows.slice((page - 1) * size, page * size).map((r) => view(server, r, false)), total: rows.length });
  }
  const row = state.rows.find((r) => r.id === id && visible(server, r));
  if (id !== undefined && !row) return failure({ status: 404, message: "not found", reason: "not_found" });
  if (method === "GET" && row) return ok(view(server, row, true));
  const role = server.memberships.find((m) => m.tenant_id === row?.tenant_id)?.role ?? "owner";
  if (row && row.created_by !== server.uploader && role !== "owner" && role !== "admin") return failure({ status: 403, message: "forbidden", reason: "forbidden" });
  if (method === "DELETE" && row) {
    state.rows = state.rows.filter((r) => r !== row);
    const chats = server.areaState<{ sessions: { id: string; chat_id: string; created_by: string }[]; messages: Record<string, unknown>; next: number }>("chat", () => ({ sessions: [], messages: {}, next: 1 }));
    for (const session of chats.sessions.filter((s) => s.chat_id === row.id)) delete chats.messages[session.id];
    chats.sessions = chats.sessions.filter((s) => s.chat_id !== row.id);
    return ok({ deleted: row.id });
  }
  if ((method !== "POST" || id !== undefined) && (method !== "PUT" || !row)) return undefined;
  const body = JSON.parse(String(config.data ?? "{}")) as Partial<AssistantRow>;
  const next = { ...(row ?? assistantRow(state.next++, { created_by: server.uploader, tenant_id: body.tenant_id ?? tenant })), ...body };
  if (state.rows.some((r) => r !== row && r.tenant_id === next.tenant_id && r.name.toLowerCase() === next.name.toLowerCase())) return failure({ status: 409, message: "duplicate name", reason: "duplicate_name" });
  const requested = body.kb_ids ?? row?.kb_ids ?? [];
  if (body.kb_ids?.some((id) => !datasetVisible(server, id))) return failure({ status: 404, message: "dataset not found", reason: "dataset_not_found" });
  const hidden = row?.kb_ids.filter((id) => server.datasets[id] && !datasetVisible(server, id)) ?? [];
  next.kb_ids = [...new Set([...hidden, ...requested])];
  if (next.permission === "team") {
    const privateIds = next.kb_ids.filter((id) => server.datasets[id]?.permission === "me");
    if (privateIds.length) return failure({ status: 409, message: "dataset not shared", reason: "assistant_dataset_not_shared", data: { dataset_ids: privateIds } });
  }
  if (row?.permission === "team" && next.permission === "me" && memberCount(server, row) > 0) return failure({ status: 409, message: "member chats", reason: "assistant_has_member_chats", data: { count: memberCount(server, row) } });
  if (body.prompt_config) next.prompt_config = { ...(row?.prompt_config ?? assistantRow().prompt_config), ...body.prompt_config };
  if (row) Object.assign(row, next); else state.rows.push(next);
  return ok(view(server, next, true));
};
