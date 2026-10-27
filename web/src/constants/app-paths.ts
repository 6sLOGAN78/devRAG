/** In-app route paths shared by pages that link to each other without importing the route registry. */
export const DATASETS_PATH = "/datasets";
export const MODEL_SETTINGS_PATH = "/user-setting/model";
const DATASET_FILES_PATH = "/dataset/files";

/** A dataset's workspace page. The id travels as `?id=` on the documented path (UI-SPEC choice 4). */
export function datasetFilesPath(id: string): string {
  return `${DATASET_FILES_PATH}?id=${encodeURIComponent(id)}`;
}

/** Route constants and builders for the Phase 4 screens; a link and its registered route share one definition. */
export const DATASET_LOGS_ROUTE = "/dataset/logs";
export const CHUNK_ROUTE = "/chunk";
export const DOCUMENT_VIEWER_ROUTE = "/document";

/** The parsing log of a dataset. */
export function datasetLogsPath(datasetId: string): string {
  return `${DATASET_LOGS_ROUTE}?id=${encodeURIComponent(datasetId)}`;
}
/** The chunks of one document. */
export function chunkPath(datasetId: string, docId: string): string {
  return `${CHUNK_ROUTE}?id=${encodeURIComponent(datasetId)}&doc=${encodeURIComponent(docId)}`;
}
/** The viewer of one document. */
export function documentViewerPath(datasetId: string, docId: string, page?: number): string {
  const suffix = page !== undefined && Number.isSafeInteger(page) && page > 0 ? `&page=${page}` : "";
  return `${DOCUMENT_VIEWER_ROUTE}?id=${encodeURIComponent(datasetId)}&doc=${encodeURIComponent(docId)}${suffix}`;
}

export const CHATS_ROUTE = "/chats";
export const DATASET_TESTING_ROUTE = "/dataset/testing";
export function chatPath(chatId: string, sessionId?: string): string {
  return `${CHATS_ROUTE}?chat=${encodeURIComponent(chatId)}${sessionId ? `&session=${encodeURIComponent(sessionId)}` : ""}`;
}
export const retrievalTestPath = (datasetId: string): string => `${DATASET_TESTING_ROUTE}?id=${encodeURIComponent(datasetId)}`;
