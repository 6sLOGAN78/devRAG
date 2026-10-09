import { ApiError } from "@/services/http";

/**
 * Which page-level state a failed dataset detail request maps to (D-27, T-03-31-01). A 404 is "Dataset not found":
 * the server answers it for a dataset that is missing, deleted, private to someone else or in a workspace the caller
 * has not joined, and the page shows one identical block for all of them. Anything else (a 5xx, a dropped connection)
 * is a failure the user can retry and says nothing about whether the dataset exists.
 */
export type DatasetPageState = "notFound" | "error";

export function datasetPageState(error: unknown): DatasetPageState {
  return error instanceof ApiError && error.status === 404 ? "notFound" : "error";
}
