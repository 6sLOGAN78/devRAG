import { ApiError } from "@/services/http";
import { reasonOf } from "@/pages/datasets/errors";
export function pageFailure(error: unknown): "gone" | "error" {
  return error instanceof ApiError && error.status === 404 ? "gone" : "error";
}
export interface CompletionFailure { kind: "alert" | "toast" | "gone"; key: string }
export function completionFailure(error: unknown): CompletionFailure {
  const alert = (key: string): CompletionFailure => ({ kind: "alert", key });
  if (!(error instanceof ApiError)) return alert("chat.error.send");
  if (error.kind === "timeout") return alert("chat.error.timeout");
  const reason = reasonOf(error), status = error.status;
  if (status === 409 && reason === "datasets_unavailable") return alert("chat.notice.noneAvailable");
  if (status === 409 && reason === "turn_in_progress") return alert("chat.error.turnBusy");
  if (status === 409 && reason === "session_full") return alert("chat.error.full");
  if ([503, 429].includes(status) && reason === "provider_rate_limited") return alert("chat.error.providerRateLimited");
  if (status === 429) return alert("chat.error.rateLimited");
  if ([400, 409].includes(status) && reason === "model_unavailable") return alert("chat.error.model");
  if (status === 502 && reason === "rerank_unavailable") return alert("chat.error.rerank");
  if (status === 503 && reason === "index_unavailable") return alert("chat.error.index");
  if ([502, 504].includes(status) && reason === "provider_timeout") return alert("chat.error.timeout");
  if (status === 400 && reason === "provider_refused") return alert("chat.error.refused");
  if (status === 403) return { kind: "toast", key: "workspace.forbidden" };
  if (status === 404) return { kind: "gone", key: "chat.gone.chat" };
  return alert("chat.error.send");
}
