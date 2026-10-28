import { chatPath, chatsPath, chatSessionPath, chatSessionsPath, messageFeedbackPath } from "@/constants/api-paths";
import { toPosition, type ChunkPosition } from "./chunk-service";
import { request } from "./http";
import { tableViewsOf, type TableView } from "./table-features";
import { asRecord, clampWhole, count, text } from "./mapping";

export interface PromptConfig { system: string; prologue: string; emptyResponse: string }
export interface AssistantView {
  id: string; name: string; permission: "me" | "team"; createdBy: string; kbIds: string[]; unavailableDatasets: number;
  llmId: string; rerankId: string; similarityThreshold: number; vectorSimilarityWeight: number; topN: number;
  promptConfig: PromptConfig; llmSetting: Record<string, number>; updateTime: number;
}
export interface AssistantDetail extends AssistantView { icon: string; membersWithChats: number }
export interface SessionView { id: string; chatId: string; name: string; createTime: number; updateTime: number }
export interface SourceHit {
  tables?: TableView[];
  chunkId: string; docId: string; docName: string; datasetId: string; content: string;
  positions: ChunkPosition[]; pageSizes: Record<string, [number, number]>;
  similarity: number | null; termSimilarity: number | null; vectorSimilarity: number | null; rerankSimilarity: number | null;
}
export type ReferenceChunk = (SourceHit & { index: number; unavailable?: false }) | { index: number; unavailable: true };
export interface Reference { chunks: ReferenceChunk[]; docAggs: { docId: string; docName: string; count: number }[] }
export interface UsageView { input: number; output: number; total: number; estimated: boolean }
export type Finish = "complete" | "stopped" | "failed";
export type Feedback = "up" | "down" | null;
export interface ChatMessage {
  id: string; role: "user" | "assistant"; content: string; createdAt: number;
  finish: Finish; reference: Reference; usage: UsageView | null; latencyMs: number | null; empty: boolean; feedback: Feedback;
}
export interface SessionDetail extends SessionView { messages: ChatMessage[]; hasEarlier: boolean }
export interface Page<T> { items: T[]; total: number }
const array = (raw: unknown): unknown[] => Array.isArray(raw) ? raw : [];
const LLM_KEYS = ["temperature", "top_p", "max_tokens", "presence_penalty", "frequency_penalty"];

export function finiteScore(raw: unknown): number | null {
  if (typeof raw !== "number" && (typeof raw !== "string" || raw.trim() === "")) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}
function settings(raw: unknown): Record<string, number> {
  const record = asRecord(raw);
  return Object.fromEntries(LLM_KEYS.flatMap((key) => {
    const value = finiteScore(record[key]); return value === null ? [] : [[key, value]];
  }));
}
export function toAssistant(raw: unknown): AssistantView {
  const d = asRecord(raw), prompt = asRecord(d.prompt_config);
  return {
    id: text(d.id), name: text(d.name), permission: d.permission === "team" ? "team" : "me", createdBy: text(d.created_by),
    kbIds: array(d.kb_ids).filter((id): id is string => typeof id === "string"), unavailableDatasets: count(d.unavailable_datasets),
    llmId: text(d.llm_id), rerankId: text(d.rerank_id), similarityThreshold: count(d.similarity_threshold),
    vectorSimilarityWeight: count(d.vector_similarity_weight), topN: count(d.top_n),
    promptConfig: { system: text(prompt.system), prologue: text(prompt.prologue), emptyResponse: text(prompt.empty_response) },
    llmSetting: settings(d.llm_setting), updateTime: count(d.update_time),
  };
}
export function toAssistantDetail(raw: unknown): AssistantDetail {
  const d = asRecord(raw);
  return { ...toAssistant(d), icon: text(d.icon), membersWithChats: count(d.members_with_chats) };
}
export function toSession(raw: unknown): SessionView {
  const d = asRecord(raw);
  return { id: text(d.id), chatId: text(d.chat_id), name: text(d.name), createTime: count(d.create_time), updateTime: count(d.update_time) };
}
/** Retrieval hits and reference passages share the same explicit source fields. */
export function toSourceHit(raw: unknown): SourceHit {
  const d = asRecord(raw);
  const sizes = Object.entries(asRecord(d.page_sizes)).filter(([, v]) => Array.isArray(v) && v.length === 2 && v.every((n) => typeof n === "number" && Number.isFinite(n)));
  return {
    ...(d.tables !== undefined ? { tables: tableViewsOf(d.tables) } : {}),
    chunkId: text(d.chunk_id), docId: text(d.doc_id), docName: text(d.doc_name), datasetId: text(d.dataset_id), content: text(d.content),
    positions: array(d.positions).map(toPosition).filter((v): v is ChunkPosition => v !== null),
    pageSizes: Object.fromEntries(sizes) as Record<string, [number, number]>,
    similarity: finiteScore(d.similarity), termSimilarity: finiteScore(d.term_similarity), vectorSimilarity: finiteScore(d.vector_similarity), rerankSimilarity: finiteScore(d.rerank_similarity),
  };
}
export function toReference(raw: unknown): Reference {
  const d = asRecord(raw);
  const chunks = array(d.chunks).flatMap((raw): ReferenceChunk[] => {
    const chunk = asRecord(raw), index = finiteScore(chunk.index);
    if (index === null || !Number.isSafeInteger(index) || index < 0) return [];
    return [chunk.unavailable === true ? { index, unavailable: true } : { ...toSourceHit(chunk), index }];
  });
  return { chunks, docAggs: array(d.doc_aggs).map((raw) => { const a = asRecord(raw); return { docId: text(a.doc_id), docName: text(a.doc_name), count: count(a.count) }; }) };
}
export const referenceChunk = (reference: Reference, index: number): ReferenceChunk | undefined => reference.chunks.find((chunk) => chunk.index === index);
export function toUsage(raw: unknown): UsageView {
  const d = asRecord(raw); return { input: count(d.input), output: count(d.output), total: count(d.total), estimated: d.estimated === true };
}
export function toMessage(raw: unknown): ChatMessage {
  const d = asRecord(raw);
  return {
    id: text(d.id), role: d.role === "assistant" ? "assistant" : "user", content: text(d.content), createdAt: count(d.created_at),
    finish: d.finish === "failed" || d.finish === "stopped" ? d.finish : "complete", reference: toReference(d.reference),
    usage: d.usage == null ? null : toUsage(d.usage), latencyMs: finiteScore(d.latency_ms), empty: d.empty === true,
    feedback: d.feedback === "up" || d.feedback === "down" ? d.feedback : null,
  };
}
export function toSessionDetail(raw: unknown): SessionDetail {
  const d = asRecord(raw); return { ...toSession(d), messages: array(d.messages).map(toMessage), hasEarlier: d.has_earlier === true };
}

export interface AssistantChanges {
  name?: string; icon?: string | null; permission?: "me" | "team"; kbIds?: string[]; llmId?: string; rerankId?: string | null;
  similarityThreshold?: number; vectorSimilarityWeight?: number; topN?: number;
  promptConfig?: Partial<PromptConfig>; llmSetting?: Record<string, number>;
}
function changesBody(changes: AssistantChanges): Record<string, unknown> {
  const fields: Record<string, keyof AssistantChanges> = {
    name: "name", icon: "icon", permission: "permission", kb_ids: "kbIds", llm_id: "llmId", rerank_id: "rerankId",
    similarity_threshold: "similarityThreshold", vector_similarity_weight: "vectorSimilarityWeight", top_n: "topN", llm_setting: "llmSetting",
  };
  const body = Object.fromEntries(Object.entries(fields).flatMap(([server, client]) => changes[client] === undefined ? [] : [[server, changes[client]]]));
  if (changes.promptConfig !== undefined) {
    const p = changes.promptConfig;
    body.prompt_config = { ...(p.system !== undefined ? { system: p.system } : {}), ...(p.prologue !== undefined ? { prologue: p.prologue } : {}), ...(p.emptyResponse !== undefined ? { empty_response: p.emptyResponse } : {}) };
  }
  return body;
}
export async function listAssistants(tenantId: string, page = 1, keywords = ""): Promise<Page<AssistantView>> {
  const d = asRecord(await request({ url: chatsPath, method: "GET", params: { tenant_id: tenantId, page: clampWhole(page, 1, Number.MAX_SAFE_INTEGER), page_size: 20, keywords: keywords.slice(0, 128) } }, { silent: true }));
  return { items: array(d.items).map(toAssistant), total: count(d.total) };
}
export async function getAssistant(chatId: string): Promise<AssistantDetail> {
  return toAssistantDetail(await request({ url: chatPath(chatId), method: "GET" }, { silent: true }));
}
export async function createAssistant(tenantId: string, changes: AssistantChanges): Promise<AssistantDetail> {
  return toAssistantDetail(await request({ url: chatsPath, method: "POST", data: { tenant_id: tenantId, ...changesBody(changes) } }, { silent: true }));
}
export async function updateAssistant(chatId: string, changes: AssistantChanges): Promise<AssistantDetail> {
  return toAssistantDetail(await request({ url: chatPath(chatId), method: "PUT", data: changesBody(changes) }, { silent: true }));
}
export async function deleteAssistant(chatId: string): Promise<void> {
  await request({ url: chatPath(chatId), method: "DELETE" }, { silent: true });
}
export async function listSessions(chatId: string, page = 1): Promise<Page<SessionView>> {
  const d = asRecord(await request({ url: chatSessionsPath(chatId), method: "GET", params: { page: clampWhole(page, 1, Number.MAX_SAFE_INTEGER), page_size: 20 } }, { silent: true }));
  return { items: array(d.items).map(toSession), total: count(d.total) };
}
export async function createSession(chatId: string, name?: string): Promise<SessionDetail> {
  return toSessionDetail(await request({ url: chatSessionsPath(chatId), method: "POST", data: name === undefined ? {} : { name } }, { silent: true }));
}
export async function getSession(chatId: string, sessionId: string, before?: string): Promise<SessionDetail> {
  return toSessionDetail(await request({ url: chatSessionPath(chatId, sessionId), method: "GET", params: { ...(before ? { before } : {}), limit: 50 } }, { silent: true }));
}
export async function deleteSession(chatId: string, sessionId: string): Promise<void> {
  await request({ url: chatSessionPath(chatId, sessionId), method: "DELETE" }, { silent: true });
}
export async function setFeedback(chatId: string, sessionId: string, messageId: string, thumb: Feedback, comment?: string): Promise<Feedback> {
  const d = asRecord(await request({ url: messageFeedbackPath(chatId, sessionId, messageId), method: "POST", data: { thumb, ...(comment !== undefined ? { comment } : {}) } }, { silent: true }));
  return d.feedback === "up" || d.feedback === "down" ? d.feedback : null;
}
