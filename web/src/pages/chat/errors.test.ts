import { describe, expect, it } from "vitest";
import { ApiError } from "@/services/http";
import { completionFailure } from "./errors";
describe("completion refusals use fixed copy", () => {
  it.each([
    [409, "datasets_unavailable", "chat.notice.noneAvailable", "alert"],
    [409, "turn_in_progress", "chat.error.turnBusy", "alert"], [409, "session_full", "chat.error.full", "alert"],
    [429, "rate_limited", "chat.error.rateLimited", "alert"], [400, "model_unavailable", "chat.error.model", "alert"], [409, "model_unavailable", "chat.error.model", "alert"],
    [502, "rerank_unavailable", "chat.error.rerank", "alert"], [503, "index_unavailable", "chat.error.index", "alert"],
    [502, "provider_timeout", "chat.error.timeout", "alert"], [504, "provider_timeout", "chat.error.timeout", "alert"],
    [400, "provider_refused", "chat.error.refused", "alert"], [503, "provider_rate_limited", "chat.error.providerRateLimited", "alert"], [429, "provider_rate_limited", "chat.error.providerRateLimited", "alert"],
    [403, "forbidden", "workspace.forbidden", "toast"], [404, "not_found", "chat.gone.chat", "gone"], [500, "unknown", "chat.error.send", "alert"],
  ])("maps %i %s", (status, reason, key, kind) => {
    expect(completionFailure(new ApiError({ status: Number(status), code: Number(status), message: "Hostile server sentence", data: { reason } }))).toEqual({ kind, key });
  });
  it("uses ApiError.kind to recognize the idle timeout", () => expect(completionFailure(new ApiError({ status: 0, code: -1, kind: "timeout", message: "any text" }))).toEqual({ kind: "alert", key: "chat.error.timeout" }));
  it("uses the fixed fallback for a network fault", () => expect(completionFailure(new ApiError({ status: 0, code: -1, kind: "network", message: "any text" }))).toEqual({ kind: "alert", key: "chat.error.send" }));
  it("never renders an unknown exception message", () => expect(completionFailure(new Error("hostile"))).toEqual({ kind: "alert", key: "chat.error.send" }));
});
