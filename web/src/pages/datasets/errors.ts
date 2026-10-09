import axios from "axios";
import { ApiError } from "@/services/http";

/**
 * How a failed dataset create is worded (D-18, UI-SPEC "Server errors").
 *
 * The server answers by HTTP status and a machine `data.reason`; this module turns the pair into one placement and one
 * locale key. Placement decides where the dialog shows it: under the Name field, under the Embedding model field, as
 * the blocked form, or as an alert. Only an alert may carry the server's own sentence (bounded, rendered as a text
 * node by the caller); every other answer has fixed copy. The settings dialog of plan 03-25 reuses this module.
 */
export type DatasetErrorTarget = "name" | "embedding" | "blocked" | "alert";

export interface DatasetFailure {
  target: DatasetErrorTarget;
  /** Locale key of the message. For an alert with `text`, this is the fallback used when the text is absent. */
  key: string;
  /** The server's sentence, for an alert on an otherwise unclassified refusal only. */
  text?: string;
}

/** Which save failed: the wording of the catch-all and index alerts differs ("wasn't created" against "weren't saved"). */
export type DatasetAction = "create" | "settings";

const MAX_SERVER_MESSAGE = 160;
const FALLBACKS: Record<DatasetAction, string> = { create: "datasets.error.createFallback", settings: "datasets.settings.failed" };
const INDEX_DOWN: Record<DatasetAction, string> = { create: "datasets.error.indexDown", settings: "datasets.settings.indexDown" };

/** The `data.reason` of an API answer, or an empty string. */
export function reasonOf(error: unknown): string {
  if (!(error instanceof ApiError)) return "";
  const data = error.data;
  if (typeof data !== "object" || data === null) return "";
  const reason = (data as Record<string, unknown>).reason;
  return typeof reason === "string" ? reason : "";
}

/** True for a request the dialog itself cancelled. Not a failure to report. */
export function isCancelled(error: unknown): boolean {
  return axios.isCancel(error);
}

function serverSentence(error: ApiError): string | undefined {
  const message = error.message.trim();
  return message !== "" && message.length <= MAX_SERVER_MESSAGE ? message : undefined;
}

/** Classifies a failed create (or settings save). Never throws and never returns server text outside an `alert`. */
export function datasetErrorTarget(error: unknown, action: DatasetAction = "create"): DatasetFailure {
  const fallback = FALLBACKS[action];
  if (!(error instanceof ApiError)) return { target: "alert", key: fallback };
  const reason = reasonOf(error);
  if (reason === "duplicate_name") return { target: "name", key: "datasets.error.duplicate" };
  if (reason === "model_unavailable") return { target: "embedding", key: "datasets.error.modelGone" };
  if (reason === "dimension_unsupported") return { target: "embedding", key: "datasets.error.dimension" };
  if (reason === "no_default_embedding") return { target: "blocked", key: "datasets.blocked.body" };
  if (reason === "embedding_locked") return { target: "embedding", key: "datasets.error.locked" };
  if (reason === "index_unavailable") return { target: "alert", key: INDEX_DOWN[action] };
  if (error.status === 403) return { target: "alert", key: "workspace.forbidden" };
  if (action === "settings" && error.status === 404) return { target: "alert", key: "datasets.settings.gone" };
  if (reason === "busy" || reason === "dataset_invalid") {
    const text = serverSentence(error);
    return text === undefined ? { target: "alert", key: fallback } : { target: "alert", key: fallback, text };
  }
  return { target: "alert", key: fallback };
}

/** What a confirmation does about a failed delete. */
export interface DeleteFailure {
  /** `forbidden`: the role changed (lost-permission alert, refetch). `gone`: already deleted elsewhere. `alert`: fixed copy. */
  kind: "forbidden" | "gone" | "alert";
  key: string;
}

/**
 * Classifies a failed delete of a dataset or a document. The server's own sentence is never shown: every answer has
 * fixed copy (checker flag 4), so a hostile or confusing server message cannot reach the dialog.
 */
export function deleteFailureOf(error: unknown, subject: "dataset" | "doc"): DeleteFailure {
  const failed = subject === "dataset" ? "datasets.delete.failed" : "datasets.documentDelete.failed";
  if (!(error instanceof ApiError)) return { kind: "alert", key: failed };
  if (error.status === 403) return { kind: "forbidden", key: "workspace.forbidden" };
  if (error.status === 404) return { kind: "gone", key: failed };
  if (reasonOf(error) === "index_unavailable") return { kind: "alert", key: "datasets.delete.indexDown" };
  return { kind: "alert", key: failed };
}
