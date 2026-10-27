import { z } from "zod";
import type { AssistantChanges, AssistantDetail } from "@/services/chat-service";

const score = z.number({ invalid_type_error: "errors.assistant.scoreRange" }).min(0, "errors.assistant.scoreRange").max(1, "errors.assistant.scoreRange").refine((n) => Math.abs(n * 20 - Math.round(n * 20)) < 1e-7, "errors.assistant.scoreRange");
export const assistantSchema = z.object({
  name: z.string().trim().min(1, "errors.assistant.nameRequired").max(128, "errors.assistant.nameMax"),
  icon: z.string(), permission: z.enum(["me", "team"]), kbIds: z.array(z.string()), llmId: z.string().min(1, "errors.assistant.modelRequired"), rerankId: z.string(),
  system: z.string().max(8000, "errors.assistant.systemMax"), prologue: z.string().max(500, "errors.assistant.prologueMax"),
  emptyResponse: z.string().min(1, "errors.assistant.emptyRequired").max(500, "errors.assistant.emptyMax").refine((value) => value.trim() !== "", "errors.assistant.emptyRequired"),
  similarityThreshold: score, vectorSimilarityWeight: score,
  topN: z.number({ invalid_type_error: "errors.assistant.topNRange" }).int("errors.assistant.topNRange").min(1, "errors.assistant.topNRange").max(30, "errors.assistant.topNRange"),
});
export type AssistantFormValues = z.infer<typeof assistantSchema>;

export function changesOf(detail: AssistantDetail, values: AssistantFormValues): AssistantChanges {
  const out: AssistantChanges = {};
  if (values.name.trim() !== detail.name) out.name = values.name.trim();
  if (values.icon !== detail.icon) out.icon = values.icon || null;
  if (values.permission !== detail.permission) out.permission = values.permission;
  if (JSON.stringify([...values.kbIds].sort()) !== JSON.stringify([...detail.kbIds].sort())) out.kbIds = values.kbIds;
  if (values.llmId !== detail.llmId) out.llmId = values.llmId;
  if (values.rerankId !== detail.rerankId) out.rerankId = values.rerankId || null;
  if (values.similarityThreshold !== detail.similarityThreshold) out.similarityThreshold = values.similarityThreshold;
  if (values.vectorSimilarityWeight !== detail.vectorSimilarityWeight) out.vectorSimilarityWeight = values.vectorSimilarityWeight;
  if (values.topN !== detail.topN) out.topN = values.topN;
  const prompt: NonNullable<AssistantChanges["promptConfig"]> = {};
  for (const key of ["system", "prologue", "emptyResponse"] as const) if (values[key] !== detail.promptConfig[key]) prompt[key] = values[key];
  if (Object.keys(prompt).length) out.promptConfig = prompt;
  return out;
}
