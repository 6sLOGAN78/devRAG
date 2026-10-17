import { describe, expect, it } from "vitest";
import { failureReasonKey, failureSentence, failureStepKey, isTerminalFailure } from "@/constants/failure-codes";
import { ApiError } from "@/services/http";
import {
  cancelFailureOf,
  chunkFailureOf,
  confirmCountsOf,
  datasetPageState,
  isTimeout,
  parseFailureOf,
  settingsFailureOf,
  switchFailureOf,
} from "./errors";

const api = (status: number, reason?: string, extra: Record<string, unknown> = {}, message = "") =>
  new ApiError({ code: status, status, message, data: reason === undefined ? undefined : { reason, ...extra } });
const timeout = () => new ApiError({ code: -1, status: 0, kind: "timeout", message: "Request timed out" });
const network = () => new ApiError({ code: -1, status: 0, kind: "network", message: "Network error" });

describe("datasetPageState", () => {
  it("keeps the Phase 3 mapping", () => {
    expect(datasetPageState(api(404))).toBe("notFound");
    expect(datasetPageState(api(500))).toBe("error");
  });
});

describe("isTimeout (FE-06)", () => {
  it("uses the error kind and status, never the text", () => {
    expect(isTimeout(timeout())).toBe(true);
    expect(isTimeout(new ApiError({ code: -1, status: 0, kind: "network", message: "Request timed out" }))).toBe(false);
    expect(isTimeout(new ApiError({ code: -1, status: 0, message: "Request timed out" }))).toBe(false);
    expect(isTimeout(api(504))).toBe(true);
    expect(isTimeout(new Error("timeout"))).toBe(false);
  });
});

describe("parseFailureOf", () => {
  const rows: Array<[string, unknown, Record<string, unknown>]> = [
    ["400 parse_unavailable", api(400, "parse_unavailable"), { key: "datasets.parse.error.unavailable" }],
    ["400 chunker_unavailable", api(400, "chunker_unavailable"), { key: "datasets.parse.error.chunker" }],
    ["409 model_unavailable", api(409, "model_unavailable"), { key: "datasets.parse.error.model" }],
    ["503 queue_unavailable", api(503, "queue_unavailable"), { key: "datasets.parse.error.queue" }],
    ["503 index_unavailable", api(503, "index_unavailable"), { key: "datasets.parse.error.index" }],
    ["429", api(429), { key: "datasets.parse.error.limited" }],
    ["403", api(403), { key: "workspace.forbidden", refetch: true }],
    ["404", api(404), { key: "datasets.files.gone", refetch: true }],
    ["409 already_running", api(409, "already_running"), { key: null, refetch: true }],
    ["timeout", timeout(), { key: "datasets.parse.error.startFallback" }],
    ["network", network(), { key: "datasets.parse.error.startFallback" }],
    ["500", api(500), { key: "datasets.parse.error.startFallback" }],
    ["not an ApiError", new Error("boom"), { key: "datasets.parse.error.startFallback" }],
  ];
  it.each(rows)("%s", (_name, error, expected) => {
    expect(parseFailureOf(error)).toMatchObject(expected);
  });
  it("is not fooled by a message that looks like another answer", () => {
    expect(parseFailureOf(api(500, undefined, {}, "parse_unavailable")).key).toBe("datasets.parse.error.startFallback");
  });
});

describe("cancelFailureOf and switchFailureOf", () => {
  it("place 403, 404 and the fallbacks", () => {
    expect(cancelFailureOf(api(403))).toMatchObject({ key: "workspace.forbidden", refetch: true });
    expect(cancelFailureOf(api(404))).toMatchObject({ key: "datasets.files.gone", refetch: true });
    expect(cancelFailureOf(timeout()).key).toBe("datasets.parse.error.cancelFallback");
    expect(switchFailureOf(api(403))).toMatchObject({ key: "workspace.forbidden", refetch: true });
    expect(switchFailureOf(api(404))).toMatchObject({ key: "datasets.files.gone", refetch: true });
    expect(switchFailureOf(api(503, "index_unavailable")).key).toBe("datasets.parse.error.index");
    expect(switchFailureOf(network()).key).toBe("datasets.parse.error.switchFallback");
  });
});

describe("settingsFailureOf", () => {
  it("places document mode answers", () => {
    expect(settingsFailureOf(api(400, "chunker_unavailable"), "document").key).toBe("datasets.chunking.error.method");
    expect(settingsFailureOf(api(409, "parse_running"), "document")).toMatchObject({ key: "datasets.chunking.error.running", refetch: true });
    expect(settingsFailureOf(api(404), "document")).toMatchObject({ key: "datasets.files.gone" });
    expect(settingsFailureOf(api(403), "document").key).toBe("workspace.forbidden");
    expect(settingsFailureOf(timeout(), "document").key).toBe("datasets.chunking.error.fallback");
  });
  it("uses dataset wording for the dataset default (Checker Flag 4)", () => {
    expect(settingsFailureOf(api(404), "dataset").key).toBe("datasets.chunking.error.datasetGone");
    expect(settingsFailureOf(api(400, "chunker_unavailable"), "dataset").key).toBe("datasets.chunking.error.method");
  });
});

describe("chunkFailureOf", () => {
  const edit: Array<[string, unknown, Record<string, unknown>]> = [
    ["client timeout", timeout(), { key: "inspector.editor.refused.timeout" }],
    ["502 provider_timeout", api(502, "provider_timeout"), { key: "inspector.editor.refused.timeout" }],
    ["504 provider_timeout", api(504, "provider_timeout"), { key: "inspector.editor.refused.timeout" }],
    ["429", api(429), { key: "inspector.editor.refused.limited" }],
    ["503 provider_rate_limited", api(503, "provider_rate_limited"), { key: "inspector.editor.refused.limited" }],
    ["409 model_unavailable", api(409, "model_unavailable"), { key: "inspector.editor.refused.model" }],
    ["400 chunk_too_long", api(400, "chunk_too_long"), { key: "inspector.editor.refused.tooLong" }],
    ["503 index_unavailable", api(503, "index_unavailable"), { key: "inspector.editor.refused.index" }],
    ["409 parse_running", api(409, "parse_running"), { key: "inspector.editor.refused.running", refetch: true }],
    ["404", api(404), { key: "inspector.editor.refused.gone", refetchOnDismiss: true }],
    ["403", api(403), { key: "workspace.forbidden" }],
    ["provider_unreachable", api(502, "provider_unreachable"), { key: "inspector.editor.refused.unreachable" }],
    ["dimension_mismatch", api(409, "dimension_mismatch"), { key: "inspector.editor.refused.dimension" }],
    ["network", network(), { key: "inspector.editor.refused.fallback" }],
    ["500", api(500), { key: "inspector.editor.refused.fallback" }],
  ];
  it.each(edit)("edit: %s", (_name, error, expected) => {
    expect(chunkFailureOf(error, "edit")).toMatchObject(expected);
  });
  it("add: a 404 means the document is gone (Checker Flag 5)", () => {
    expect(chunkFailureOf(api(404), "add").key).toBe("inspector.editor.refused.documentGone");
  });
  it("switch: maps the editor answers and falls back to the one toast", () => {
    expect(chunkFailureOf(api(403), "switch").key).toBe("workspace.forbidden");
    expect(chunkFailureOf(api(404), "switch").key).toBe("inspector.editor.refused.gone");
    expect(chunkFailureOf(api(409, "parse_running"), "switch").key).toBe("inspector.editor.refused.running");
    expect(chunkFailureOf(api(503, "index_unavailable"), "switch").key).toBe("inspector.editor.refused.index");
    expect(chunkFailureOf(network(), "switch").key).toBe("inspector.switch.failed");
  });
  it("a provider refusal carries bounded server text and is never a session event", () => {
    const refused = chunkFailureOf(api(400, "provider_refused", { detail: "x".repeat(500) }, "401 Unauthorized"), "edit");
    expect(refused.key).toBe("inspector.editor.refused.provider");
    expect(refused.detail).toHaveLength(300);
    expect(refused.sessionEvent).toBe(false);
    expect(chunkFailureOf(api(400, "provider_refused"), "edit").detail).toBeUndefined();
  });
});

describe("confirmCountsOf", () => {
  it("is the service function, empty for anything else", () => {
    const refusal = api(409, "confirm_required", { documents: [{ id: "d1", name: "a.pdf", chunk_count: 4, edited_count: 1, manual_count: 2 }] });
    expect(confirmCountsOf(refusal)).toEqual([{ id: "d1", name: "a.pdf", chunkCount: 4, editedCount: 1, manualCount: 2 }]);
    expect(confirmCountsOf(api(409, "already_running"))).toEqual([]);
    expect(confirmCountsOf(new Error("x"))).toEqual([]);
  });
});

describe("failure code maps", () => {
  const codes: Record<string, string> = {
    no_readable_text: "noText",
    unsupported_type: "unsupported",
    chunker_unavailable: "chunker",
    file_damaged: "damaged",
    file_too_large: "tooLarge",
    archive_limits_exceeded: "archive",
    provider_timeout: "providerTimeout",
    provider_rate_limited: "providerLimited",
    provider_unreachable: "providerUnreachable",
    provider_refused: "providerRefused",
    model_unavailable: "model",
    dimension_mismatch: "dimension",
    index_unavailable: "indexDown",
    storage_unavailable: "storage",
    worker_lost: "workerLost",
    too_many_chunks: "tooManyChunks",
    queue_unavailable: "queue",
    document_deleted: "documentGone",
    unexpected: "unknown",
  };
  it.each(Object.entries(codes))("%s", (code, leaf) => {
    expect(failureReasonKey(code)).toBe(`datasets.details.reason.${leaf}`);
  });
  it("falls back to unknown", () => {
    expect(failureReasonKey("whatever")).toBe("datasets.details.reason.unknown");
  });
  it("maps steps, with the worker's names", () => {
    const steps: Record<string, string> = { queue: "queue", fetch: "fetch", parse: "read", chunk: "split", read: "read", split: "split", embed: "embed", index: "index" };
    for (const [step, leaf] of Object.entries(steps)) expect(failureStepKey(step)).toBe(`datasets.details.step.${leaf}`);
    expect(failureStepKey("nope")).toBe("datasets.details.step.unknown");
  });
  it("marks too_many_chunks terminal", () => {
    expect(isTerminalFailure("too_many_chunks")).toBe(true);
    expect(isTerminalFailure("worker_lost")).toBe(false);
  });
  it("uses the server message only for an unknown code and only within 1 to 300 characters", () => {
    expect(failureSentence({ code: "no_readable_text", message: "server words" })).toEqual({ key: "datasets.details.reason.noText" });
    expect(failureSentence({ code: "novel", message: "Plain words." })).toEqual({ text: "Plain words." });
    expect(failureSentence({ code: "novel", message: "" })).toEqual({ key: "datasets.details.reason.unknown" });
    expect(failureSentence({ code: "novel", message: "x".repeat(301) })).toEqual({ key: "datasets.details.reason.unknown" });
    expect(failureSentence({ code: "novel", message: "x".repeat(300) })).toEqual({ text: "x".repeat(300) });
    expect(failureSentence(null)).toEqual({ key: "datasets.details.reason.unknown" });
  });
});
