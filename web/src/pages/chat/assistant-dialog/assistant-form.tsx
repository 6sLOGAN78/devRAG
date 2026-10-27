import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useEffect, useId, useRef, useState, type MutableRefObject } from "react";
import { useForm, type FieldPathValue } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { LlmSelect } from "@/components/llm-select";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ChoiceGroup } from "@/components/ui/choice-group";
import { DialogClose, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RangeField } from "@/components/ui/range-field";
import { Textarea } from "@/components/ui/textarea";
import { useCreateAssistant, useUpdateAssistant } from "@/hooks/use-chat-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import defaults from "@/locales/areas/en/assistant.json";
import type { AssistantChanges, AssistantDetail } from "@/services/chat-service";
import type { DatasetView } from "@/services/dataset-service";
import type { ModelView } from "@/services/model-service";
import { notifySuccess } from "@/services/notify";
import { useUserStore } from "@/stores/user-store";
import { AvatarPicker } from "./avatar-picker";
import { DatasetChecklist } from "./dataset-checklist";
import { assistantErrorTarget } from "./errors";
import { assistantSchema, changesOf, type AssistantFormValues } from "./schemas";

export interface SavedAssistant { id: string; created?: boolean; leftList?: boolean }
interface Props {
  assistant?: AssistantDetail; models: readonly ModelView[]; rerankModels: readonly ModelView[]; datasets: DatasetView[];
  pendingRef: MutableRefObject<boolean>; onClose: () => void; onSaved: (saved: SavedAssistant) => void;
  refetchDatasets: () => unknown; refetchModels: () => unknown;
}
export function AssistantForm({ assistant, models, rerankModels, datasets, pendingRef, onClose, onSaved, refetchDatasets, refetchModels }: Props) {
  const { t } = useTranslation(), base = useId();
  const workspace = useActiveWorkspace(), userId = useUserStore((s) => s.user?.id);
  const create = useCreateAssistant(), update = useUpdateAssistant();
  const inFlight = useRef(false), mounted = useRef(true);
  const [busy, setBusy] = useState(false), [pictureBusy, setPictureBusy] = useState(false);
  const [alert, setAlert] = useState<string | null>(null), [flaggedIds, setFlaggedIds] = useState<string[]>([]);
  const form = useForm<AssistantFormValues>({ resolver: zodResolver(assistantSchema), mode: "onSubmit", reValidateMode: "onChange", defaultValues: {
    name: assistant?.name ?? "", icon: assistant?.icon ?? "", permission: assistant?.permission ?? "me", kbIds: assistant?.kbIds ?? [],
    llmId: assistant?.llmId ?? models[0]?.id ?? "", rerankId: assistant?.rerankId ?? "",
    system: assistant?.promptConfig.system ?? defaults.assistant.default.system,
    prologue: assistant?.promptConfig.prologue ?? t("assistant.default.prologue"), emptyResponse: assistant?.promptConfig.emptyResponse ?? t("assistant.default.empty"),
    similarityThreshold: assistant?.similarityThreshold ?? 0.2, vectorSimilarityWeight: assistant?.vectorSimilarityWeight ?? 0.3, topN: assistant?.topN ?? 6,
  } });
  const values = form.watch(), errors = form.formState.errors;
  const changed = assistant ? Object.keys(changesOf(assistant, values)).length > 0 : true;
  const valid = assistantSchema.safeParse(values).success;
  const privateSelected = datasets.some((d) => d.permission !== "team" && values.kbIds.includes(d.id));
  useEffect(() => { mounted.current = true; form.setFocus("name"); return () => { mounted.current = false; }; }, [form]);
  const id = (field: keyof AssistantFormValues) => `${base}-${field}`;
  const message = (field: keyof AssistantFormValues) => {
    const key = errors[field]?.message;
    return typeof key === "string" && key ? <p id={`${id(field)}-error`} role="alert" className="text-xs text-destructive">{t(key, { name: values.name.trim() })}</p> : null;
  };
  const edit = (field: keyof AssistantFormValues) => {
    setAlert(null); setFlaggedIds([]);
    if (form.getFieldState(field).error?.type === "server") form.clearErrors(field);
  };
  const set = <K extends keyof AssistantFormValues>(field: K, value: FieldPathValue<AssistantFormValues, K>) => { edit(field); form.setValue(field, value, { shouldDirty: true, shouldValidate: true }); };
  async function submit(submitted: AssistantFormValues) {
    if (inFlight.current || pictureBusy) return;
    const visible = new Set(datasets.map((d) => d.id));
    const values = { ...submitted, kbIds: submitted.kbIds.filter((id) => visible.has(id)) };
    const changes: AssistantChanges = assistant ? changesOf(assistant, values) : {
      name: values.name, icon: values.icon || null, permission: values.permission, kbIds: values.kbIds, llmId: values.llmId, rerankId: values.rerankId || null,
      similarityThreshold: values.similarityThreshold, vectorSimilarityWeight: values.vectorSimilarityWeight, topN: values.topN,
      promptConfig: { system: values.system, prologue: values.prologue, emptyResponse: values.emptyResponse },
    };
    if (assistant && !Object.keys(changes).length) return;
    inFlight.current = true; pendingRef.current = true; setBusy(true); setAlert(null); setFlaggedIds([]); form.clearErrors();
    const narrowed = assistant?.permission === "team" && values.permission === "me" && assistant.createdBy !== userId;
    try {
      const result = assistant ? await update.mutateAsync({ chatId: assistant.id, changes }) : await create.mutateAsync(changes);
      if (!mounted.current) return;
      notifySuccess(t(narrowed ? "assistant.saved.narrowed" : assistant ? "assistant.saved.updated" : "assistant.saved.created"));
      onSaved(narrowed ? { id: result.id, leftList: true } : { id: result.id, created: !assistant }); onClose();
    } catch (error) {
      if (!mounted.current) return;
      const failure = assistantErrorTarget(error);
      if (failure.datasetIds) setFlaggedIds(failure.datasetIds);
      if (failure.target === "alert") setAlert(t(failure.key, { count: failure.count, workspace: workspace?.name }));
      else {
        if (failure.target === "llmId") { form.setValue("llmId", ""); void refetchModels(); }
        if (failure.target === "kbIds") void refetchDatasets();
        form.setError(failure.target, { type: "server", message: failure.key });
        if (failure.target === "name") form.setFocus("name");
      }
    } finally { inFlight.current = false; pendingRef.current = false; if (mounted.current) setBusy(false); }
  }
  return <form noValidate data-testid="assistant-form" aria-busy={busy || undefined} className="flex min-h-0 flex-col gap-4" onSubmit={form.handleSubmit(submit)}>
    <DialogHeader><DialogTitle>{t(assistant ? "assistant.dialog.titleSettings" : "assistant.dialog.titleCreate")}</DialogTitle><DialogDescription>{assistant?.name ?? t("assistant.field.datasetsHelp")}</DialogDescription></DialogHeader>
    <div className="flex max-h-[calc(100dvh-14rem)] flex-col gap-6 overflow-y-auto pr-1">
      {alert ? <Alert data-testid="assistant-error">{alert}</Alert> : null}
      <fieldset className="grid gap-4"><legend className="mb-2 text-sm font-semibold">{t("assistant.group.basics")}</legend>
        <div className="grid gap-1"><Label htmlFor={id("name")}>{t("assistant.field.name")}</Label><Input {...form.register("name", { onChange: () => edit("name") })} id={id("name")} data-testid="field-assistant-name" readOnly={busy} autoComplete="off" aria-invalid={Boolean(errors.name)} aria-describedby={errors.name ? `${id("name")}-error` : undefined} />{message("name")}</div>
        <AvatarPicker name={values.name} value={values.icon} onChange={(value) => set("icon", value)} disabled={busy} onBusyChange={setPictureBusy} />
        <ChoiceGroup testId="assistant-visibility" legend={t("assistant.field.visibility")} name={`${base}-visibility`} value={values.permission} onChange={(value) => set("permission", value === "team" ? "team" : "me")} disabled={busy} options={[
          { value: "me", title: t("assistant.visibility.meTitle"), description: t("assistant.visibility.meBody"), testId: "assistant-visibility-me" },
          { value: "team", title: t("assistant.visibility.teamTitle"), description: t("assistant.visibility.teamBody", { workspace: workspace?.name }), disabled: privateSelected, badge: privateSelected ? t("assistant.visibility.needsShared") : undefined, testId: "assistant-visibility-team" },
        ]} />
        {privateSelected ? <p data-testid="assistant-share-reason" className="text-xs text-muted-foreground">{t("assistant.visibility.reason")}</p> : null}
        {assistant?.permission === "team" ? <Alert variant="info" data-testid="assistant-narrowing-info"><p>{t("assistant.visibility.narrowingInfo")}</p>{assistant.createdBy !== userId ? <p>{t("assistant.visibility.narrowingCreator")}</p> : null}</Alert> : null}
      </fieldset>
      <fieldset disabled={busy} className="grid gap-2"><legend className="mb-2 text-sm font-semibold">{t("assistant.group.knowledge")}</legend>
        <DatasetChecklist datasets={datasets} selected={values.kbIds} permission={values.permission} unavailableCount={assistant?.unavailableDatasets ?? 0} flaggedIds={flaggedIds}
          onToggle={(id, checked) => set("kbIds", checked ? [...values.kbIds, id] : values.kbIds.filter((value) => value !== id))} />{message("kbIds")}
      </fieldset>
      <fieldset className="grid gap-4"><legend className="mb-2 text-sm font-semibold">{t("assistant.group.model")}</legend>
        <div className="grid gap-1"><Label htmlFor={id("llmId")}>{t("assistant.field.model")}</Label><LlmSelect id={id("llmId")} models={models} type="chat" value={values.llmId} onChange={(value) => set("llmId", value)} disabled={busy} data-testid="field-assistant-model" aria-invalid={Boolean(errors.llmId)} /><p className="text-xs text-muted-foreground">{t("assistant.field.modelHelp")}</p>{message("llmId")}</div>
        {([ ["system", "system", 8000, 4], ["prologue", "prologue", 500, 2], ["emptyResponse", "empty", 500, 2] ] as const).map(([field, key, max, rows]) => <div key={field} className="grid gap-1">
          <Label htmlFor={id(field)}>{t(`assistant.field.${key}`)}</Label><Textarea {...form.register(field, { onChange: () => edit(field) })} id={id(field)} rows={rows} maxLength={max} readOnly={busy} className={field === "system" ? "min-h-32 max-h-64 resize-y" : undefined} data-testid={`field-assistant-${key}`} aria-invalid={Boolean(errors[field])} aria-describedby={`${id(field)}-help${errors[field] ? ` ${id(field)}-error` : ""}`} />
          <p id={`${id(field)}-help`} className="text-xs text-muted-foreground">{t(`assistant.field.${key}Help`)}</p>{message(field)}
        </div>)}
      </fieldset>
      <fieldset className="grid gap-4"><legend className="mb-2 text-sm font-semibold">{t("assistant.group.retrieval")}</legend>
        <RangeField id={id("similarityThreshold")} testId="field-assistant-threshold" label={t("assistant.field.threshold")} helper={t("assistant.field.thresholdHelp")} lowLabel={t("assistant.field.thresholdLow")} highLabel={t("assistant.field.thresholdHigh")} min={0} max={1} step={0.05} value={values.similarityThreshold} readout={values.similarityThreshold.toFixed(2)} onChange={(value) => set("similarityThreshold", value)} disabled={busy} />
        <RangeField id={id("vectorSimilarityWeight")} testId="field-assistant-weight" label={t("assistant.field.weight")} helper={t("assistant.field.weightHelp")} lowLabel={t("assistant.field.weightLow")} highLabel={t("assistant.field.weightHigh")} min={0} max={1} step={0.05} value={values.vectorSimilarityWeight} readout={t("assistant.field.weightValue", { keyword: Math.round((1 - values.vectorSimilarityWeight) * 100), vector: Math.round(values.vectorSimilarityWeight * 100) })} onChange={(value) => set("vectorSimilarityWeight", value)} disabled={busy} />
        <div className="grid gap-1"><Label htmlFor={id("topN")}>{t("assistant.field.topN")}</Label><Input {...form.register("topN", { valueAsNumber: true, onChange: () => edit("topN") })} id={id("topN")} type="number" inputMode="numeric" min={1} max={30} step={1} data-testid="field-assistant-topn" readOnly={busy} aria-invalid={Boolean(errors.topN)} /><p className="text-xs text-muted-foreground">{t("assistant.field.topNHelp")}</p>{message("topN")}</div>
        <div className="grid gap-1"><Label htmlFor={id("rerankId")}>{t("assistant.field.rerank")}</Label><LlmSelect id={id("rerankId")} models={rerankModels} type="rerank" value={values.rerankId} onChange={(value) => set("rerankId", value)} notSetLabel={t("assistant.field.rerankNone")} disabled={busy} data-testid="field-assistant-rerank" /><p className="text-xs text-muted-foreground">{t("assistant.field.rerankHelp")}</p></div>
      </fieldset>
    </div>
    <DialogFooter><DialogClose asChild><Button type="button" variant="ghost" data-testid="assistant-close">{t("dialog.close")}</Button></DialogClose>
      <Button type="submit" data-testid="assistant-submit" aria-disabled={busy || pictureBusy || !valid || !changed} aria-busy={busy || undefined}>{busy ? <Loader2 aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" /> : null}{t(assistant ? "assistant.dialog.submitSave" : "assistant.dialog.submitCreate")}</Button>
    </DialogFooter>
  </form>;
}
