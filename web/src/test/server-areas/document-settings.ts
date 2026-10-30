import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from "axios";
import type { AreaHandler, DatasetServer } from "../dataset-server";
import { documentDetailOf, setDatasetDefaults, setFileExtra } from "./files";
import { isImplemented } from "@/constants/chunk-methods";

/**
 * Test-server area for chunking settings (R-167): `PATCH .../documents/{doc}` for one document and the chunking keys of
 * `PUT .../datasets/{id}` for the dataset default. It validates like the server's `ParserConfig` (BE-09), refuses an
 * unbuilt method with `chunker_unavailable` and a document that is parsing with 409 `parse_running`. Its writes land in
 * the `files` area state, so the document detail and the dataset detail show them. Fake data only.
 */

const DELIMITER_MAX = 64;

export interface SettingsRefusal {
  status: number;
  reason: string;
  /** `data.field` of a `parser_config_invalid` answer: `chunk_token_num`, `delimiter` or `overlapped_percent`. */
  field?: string;
}

interface SettingsState {
  refuse: SettingsRefusal | null;
}

const stateOf = (server: DatasetServer): SettingsState => server.areaState<SettingsState>("document-settings", () => ({ refuse: null }));

/** The next settings save (document or dataset) is refused once with this answer. */
export function refuseNextSettings(server: DatasetServer, refusal: SettingsRefusal): void {
  stateOf(server).refuse = refusal;
}

function refuse(config: InternalAxiosRequestConfig, status: number, reason: string, field?: string): Promise<never> {
  const body = { code: status, message: reason, data: field === undefined ? { reason } : { reason, field } };
  const response = { data: body, status, statusText: String(status), headers: new AxiosHeaders(), config } as never;
  return Promise.reject(new AxiosError(`status ${status}`, "ERR_BAD_RESPONSE", config, null, response));
}

const isWhole = (value: unknown, min: number, max: number): value is number => typeof value === "number" && Number.isInteger(value) && value >= min && value <= max;

/** The first bad key of a `parser_config` object, or null. */
function badField(config: Record<string, unknown>): string | null {
  if ("auto_keywords" in config && !isWhole(config.auto_keywords, 0, 32)) return "auto_keywords";
  if ("auto_questions" in config && !isWhole(config.auto_questions, 0, 16)) return "auto_questions";
  if ("chunk_token_num" in config && !isWhole(config.chunk_token_num, 1, 8192)) return "chunk_token_num";
  if ("delimiter" in config && !(typeof config.delimiter === "string" && [...config.delimiter].length >= 1 && [...config.delimiter].length <= DELIMITER_MAX)) return "delimiter";
  if ("overlapped_percent" in config && !isWhole(config.overlapped_percent, 0, 50)) return "overlapped_percent";
  if ("pages" in config && (!Array.isArray(config.pages) || config.pages.length > 128 || config.pages.some((pair: unknown) =>
    !Array.isArray(pair) || pair.length !== 2 || !isWhole(pair[0], 1, 1_000_000) || !isWhole(pair[1], pair[0], 1_000_000)))) return "pages";
  return null;
}

function bodyOf(config: InternalAxiosRequestConfig): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(String(config.data));
    return typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

const DOCUMENT_ROUTE = /^\/api\/v1\/datasets\/([^/]+)\/documents\/([^/]+)$/;
const DATASET_ROUTE = /^\/api\/v1\/datasets\/([^/]+)$/;

function checked(config: InternalAxiosRequestConfig, server: DatasetServer, sent: Record<string, unknown>): Promise<never> | null {
  const pending = stateOf(server).refuse;
  if (pending !== null) {
    stateOf(server).refuse = null;
    return refuse(config, pending.status, pending.reason, pending.field);
  }
  if (typeof sent.parser_id === "string" && !isImplemented(sent.parser_id)) return refuse(config, 400, "chunker_unavailable");
  const parserConfig = sent.parser_config;
  if (parserConfig !== undefined) {
    if (typeof parserConfig !== "object" || parserConfig === null) return refuse(config, 400, "parser_config_invalid");
    const field = badField(parserConfig as Record<string, unknown>);
    if (field !== null) return refuse(config, 400, "parser_config_invalid", field);
  }
  return null;
}

function valuesOf(parserConfig: unknown) {
  const source = typeof parserConfig === "object" && parserConfig !== null ? (parserConfig as Record<string, unknown>) : {};
  return {
    ...(typeof source.auto_keywords === "number" ? {autoKeywords:source.auto_keywords} : {}),
    ...(typeof source.auto_questions === "number" ? {autoQuestions:source.auto_questions} : {}),
    ...(typeof source.resume_model === "string" ? {resumeModel:source.resume_model} : {}),
    ...(typeof source.resume_use_model === "boolean" ? {resumeUseModel:source.resume_use_model} : {}),
    ...(typeof source.layout_recognize === "boolean" || typeof source.layout_recognize === "string" ? { layoutRecognize: source.layout_recognize } : {}),
    ...(Array.isArray(source.pages) ? { pages: source.pages as [number, number][] } : {}),
    ...(typeof source.chunk_token_num === "number" ? { chunkTokenNum: source.chunk_token_num } : {}),
    ...(typeof source.delimiter === "string" ? { delimiter: source.delimiter } : {}),
    ...(typeof source.overlapped_percent === "number" ? { overlappedPercent: source.overlapped_percent } : {}),
  };
}

export const handle: AreaHandler = ({ server, config, method, url, ok }) => {
  const document = DOCUMENT_ROUTE.exec(url);
  if (document && document[2] !== "metadatas" && method === "PATCH") {
    const list = server.documents[document[1] as string] ?? [];
    const row = list.find((candidate) => candidate.id === document[2]);
    if (!server.datasets[document[1] as string] || !row) return refuse(config, 404, "not_found");
    const sent = bodyOf(config);
    const refusal = checked(config, server, sent);
    if (refusal !== null) return refusal;
    if (row.run === "1") return refuse(config, 409, "parse_running");
    if (typeof sent.parser_id === "string") row.parser_id = sent.parser_id;
    setFileExtra(server, row.id, valuesOf(sent.parser_config));
    return ok(documentDetailOf(server, row));
  }
  const dataset = DATASET_ROUTE.exec(url);
  if (dataset && method === "PUT") {
    const row = server.datasets[dataset[1] as string];
    const sent = bodyOf(config);
    if (!row || (sent.parser_id === undefined && sent.parser_config === undefined)) return undefined;
    const refusal = checked(config, server, sent);
    if (refusal !== null) return refusal;
    const next = setDatasetDefaults(server, row.id, { ...(typeof sent.parser_id === "string" ? { parserId: sent.parser_id } : {}), ...valuesOf(sent.parser_config) });
    return ok({ ...row, doc_num: (server.documents[row.id] ?? []).length, chunk_num: 0, token_num: 0, language: "English", parser_id: next.parserId, create_time: row.update_time });
  }
  return undefined;
};
