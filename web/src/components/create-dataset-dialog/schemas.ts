import { z } from "zod";

/** Bounds of the create form (UI-SPEC; the API accepts the same, plan 03-14). */
export const NAME_MAX = 128;
export const DESCRIPTION_MAX = 500;
/** The live "{count}/500" caption appears from this many characters. */
export const DESCRIPTION_COUNT_FROM = 400;

export const PERMISSIONS = ["me", "team"] as const;
export type Permission = (typeof PERMISSIONS)[number];

/**
 * The dataset form, shared by the create dialog and the settings dialog of plan 03-25. Messages are locale keys,
 * translated by `FormMessage`. The name is trimmed before the length rules, so a blank name is "required".
 */
export const datasetSchema = z.object({
  name: z.string().trim().min(1, "errors.dataset.nameRequired").max(NAME_MAX, "errors.dataset.nameMax"),
  description: z.string().max(DESCRIPTION_MAX, "errors.dataset.descriptionMax"),
  embedding: z.string().min(1, "errors.dataset.embeddingRequired"),
  permission: z.enum(PERMISSIONS),
});

export type DatasetFormValues = z.infer<typeof datasetSchema>;
