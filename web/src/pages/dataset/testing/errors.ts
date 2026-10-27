import { reasonOf } from "@/pages/datasets/errors";
import { ApiError } from "@/services/http";
import { asRecord } from "@/services/mapping";

export function retrievalFailure(error: unknown): { kind: "alert" | "question" | "not-found"; key: string } {
  const alert = (key: string) => ({ kind: "alert" as const, key });
  if (!(error instanceof ApiError)) return alert("retrieval.error.fallback");
  if (error.kind === "timeout") return alert("retrieval.error.timeout");
  const reason = reasonOf(error), status = error.status, data = asRecord(error.data), question = asRecord(data.fields).question;
  if (status === 404) return { kind: "not-found", key: "" };
  if (status === 400 && (question !== undefined || reason === "question_invalid")) return { kind: "question", key: ["string_too_long", "too_long", "max_length"].includes(String(question)) ? "errors.retrieval.questionMax" : "errors.retrieval.questionRequired" };
  if ([400, 409].includes(status) && reason === "model_unavailable") return alert("retrieval.error.model");
  if (status === 502 && reason === "rerank_unavailable") return alert("retrieval.error.rerank");
  if (status === 503 && reason === "index_unavailable") return alert("retrieval.error.index");
  if (status === 429 || status === 503 && reason === "provider_rate_limited") return alert("retrieval.error.limited");
  if ([502, 504].includes(status) && reason === "provider_timeout") return alert("retrieval.error.timeout");
  if (status === 403) return alert("workspace.forbidden");
  return alert("retrieval.error.fallback");
}
