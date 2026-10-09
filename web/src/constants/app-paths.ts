/** In-app route paths shared by pages that link to each other without importing the route registry. */
export const DATASETS_PATH = "/datasets";
export const MODEL_SETTINGS_PATH = "/user-setting/model";
const DATASET_FILES_PATH = "/dataset/files";

/** A dataset's workspace page. The id travels as `?id=` on the documented path (UI-SPEC choice 4). */
export function datasetFilesPath(id: string): string {
  return `${DATASET_FILES_PATH}?id=${encodeURIComponent(id)}`;
}
