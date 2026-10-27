import { describe, expect, it } from "vitest";
import { ApiError } from "@/services/http";
import { retrievalFailure } from "./errors";
describe("retrieval refusal placement", () => {
  it.each([
    [400, "model_unavailable", "retrieval.error.model"], [409, "model_unavailable", "retrieval.error.model"],
    [502, "rerank_unavailable", "retrieval.error.rerank"], [503, "index_unavailable", "retrieval.error.index"],
    [503, "provider_rate_limited", "retrieval.error.limited"], [429, "provider_rate_limited", "retrieval.error.limited"], [429, "rate_limited", "retrieval.error.limited"],
    [502, "provider_timeout", "retrieval.error.timeout"], [504, "provider_timeout", "retrieval.error.timeout"],
    [400, "provider_refused", "retrieval.error.fallback"], [403, "forbidden", "workspace.forbidden"], [500, "unknown", "retrieval.error.fallback"],
  ])("maps %i %s to fixed copy", (status, reason, key) => expect(retrievalFailure(new ApiError({ status: Number(status), code: Number(status), message: "Hostile server sentence", data: { reason } }))).toEqual({ kind: "alert", key }));
  it("marks a 404 as not found", () => expect(retrievalFailure(new ApiError({ code: 404, status: 404, message: "gone" })).kind).toBe("not-found"));
  it("uses the typed client timeout", () => expect(retrievalFailure(new ApiError({ code: -1, status: 0, kind: "timeout", message: "arbitrary" })).key).toBe("retrieval.error.timeout"));
  it("does not infer a timeout from a sentence", () => expect(retrievalFailure(new Error("timeout")).key).toBe("retrieval.error.fallback"));
  it("places a question field refusal under Question", () => expect(retrievalFailure(new ApiError({ code: 400, status: 400, message: "invalid", data: { reason: "fields_invalid", fields: { question: "string_too_long" } } }))).toEqual({ kind: "question", key: "errors.retrieval.questionMax" }));
});
