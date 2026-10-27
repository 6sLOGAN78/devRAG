import { ApiError } from "@/services/http";
import { asRecord, count, text } from "@/services/mapping";

export interface AssistantFailure {
  target: "name" | "llmId" | "kbIds" | "alert";
  key: string;
  count?: number;
  datasetIds?: string[];
}
export function assistantErrorTarget(error: unknown): AssistantFailure {
  const fallback: AssistantFailure = { target: "alert", key: "assistant.error.fallback" };
  if (!(error instanceof ApiError)) return fallback;
  const data = asRecord(error.data), reason = text(data.reason);
  if (error.status === 409 && reason === "duplicate_name") return { target: "name", key: "assistant.error.duplicate" };
  if (error.status === 409 && reason === "assistant_dataset_not_shared") return {
    target: "alert", key: "assistant.error.notShared", datasetIds: Array.isArray(data.dataset_ids) ? data.dataset_ids.filter((id): id is string => typeof id === "string") : [],
  };
  if (error.status === 409 && reason === "assistant_has_member_chats") return { target: "alert", key: "assistant.error.narrowing", count: Math.max(0, Math.floor(count(data.count))) };
  if (error.status === 404 && reason === "dataset_not_found") return { target: "kbIds", key: "assistant.error.dataset" };
  if ([400, 409].includes(error.status) && reason === "model_unavailable") return { target: "llmId", key: "assistant.error.model" };
  if (error.status === 403) return { target: "alert", key: "workspace.forbidden" };
  if (error.status === 404) return { target: "alert", key: "assistant.error.gone" };
  return fallback;
}
