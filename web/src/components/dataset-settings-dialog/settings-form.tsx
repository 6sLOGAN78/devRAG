import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { Info, Loader2 } from "lucide-react";
import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { DESCRIPTION_COUNT_FROM, DESCRIPTION_MAX, datasetSchema, type DatasetFormValues } from "@/components/create-dataset-dialog/schemas";
import { ServerFieldError } from "@/components/create-dataset-dialog/server-field-error";
import { LlmSelect } from "@/components/llm-select";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ChoiceGroup } from "@/components/ui/choice-group";
import { DialogClose, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useWorkspaceName } from "@/hooks/use-dataset-permissions";
import { refreshDataset, useUpdateDatasetRequest } from "@/hooks/use-knowledge-request";
import { modelsKeyRoot } from "@/hooks/use-llm-request";
import { datasetErrorTarget, isCancelled } from "@/pages/datasets/errors";
import type { DatasetChanges, DatasetView } from "@/services/dataset-service";
import type { ModelView } from "@/services/model-service";
import { notifySuccess } from "@/services/notify";

export interface SettingsFormProps {
  dataset: DatasetView;
  /** The embedding model is fixed once the dataset has documents or chunks: shown read-only, never sent. */
  locked: boolean;
  /** The workspace's embedding models, live: a refetch after a refusal updates the select. Empty when locked. */
  models: readonly ModelView[];
  /** True while a save is in flight: the dialog then ignores Esc and outside clicks. */
  pendingRef: MutableRefObject<boolean>;
  onClose: () => void;
}

type FieldAnswer = { field: "name" | "embedding"; text: string };

/** `team` or `me`; anything else the server might send is shown as the narrower choice. */
function permissionOf(dataset: DatasetView): "me" | "team" {
  return dataset.permission === "team" ? "team" : "me";
}

/** The fields whose value differs from the dataset: exactly what the PUT carries (KB-06). */
function changesOf(dataset: DatasetView, values: DatasetFormValues, locked: boolean): DatasetChanges {
  const changes: DatasetChanges = {};
  const name = values.name.trim();
  if (name !== dataset.name) changes.name = name;
  const description = values.description.trim();
  if (description !== dataset.description.trim()) changes.description = description === "" ? null : description;
  if (values.permission !== permissionOf(dataset)) changes.permission = values.permission;
  if (!locked && values.embedding !== dataset.embdId) changes.embdId = values.embedding;
  return changes;
}

/** The model's display name: the part of the composite id before the provider. */
function modelName(embdId: string): string {
  const at = embdId.lastIndexOf("@");
  return at > 0 ? embdId.slice(0, at) : embdId;
}

/**
 * The settings form: name, description, visibility and the embedding model (UI-SPEC "Dataset settings dialog"). Only
 * the changed fields are sent. Server refusals are placed by `datasetErrorTarget`, as in the create dialog; a second
 * submit while one is in flight is ignored. Save stays `aria-disabled` until something differs from the dataset.
 */
export function SettingsForm({ dataset, locked, models, pendingRef, onClose }: SettingsFormProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const update = useUpdateDatasetRequest();
  const workspaceName = useWorkspaceName(dataset.tenantId);
  const form = useForm<DatasetFormValues>({
    resolver: zodResolver(datasetSchema),
    mode: "onSubmit",
    reValidateMode: "onChange",
    defaultValues: { name: dataset.name, description: dataset.description, embedding: dataset.embdId, permission: permissionOf(dataset) },
  });
  const nameInput = useRef<HTMLInputElement | null>(null);
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState<string | null>(null);
  const [answer, setAnswer] = useState<FieldAnswer | null>(null);
  const values = form.watch();
  const changed = Object.keys(changesOf(dataset, values, locked)).length > 0;
  const narrowing = permissionOf(dataset) === "team" && values.permission === "me";

  useEffect(() => {
    nameInput.current?.focus();
  }, []);

  function clearAnswers(field?: FieldAnswer["field"]): void {
    setAlert(null);
    setAnswer((current) => (field === undefined || current?.field === field ? null : current));
  }

  function fail(error: unknown, name: string): void {
    if (isCancelled(error)) return;
    const failure = datasetErrorTarget(error, "settings");
    // A refusal can mean the cache is stale (permission, documents or the dataset itself changed): fetch it again.
    if (failure.key === "workspace.forbidden" || failure.key === "datasets.error.locked" || failure.key === "datasets.settings.gone") {
      void refreshDataset(queryClient, dataset.tenantId, dataset.id);
    }
    if (failure.target === "name") {
      setAnswer({ field: "name", text: t(failure.key, { name }) });
      form.setError("name", { type: "server", message: "" });
      form.setFocus("name");
      return;
    }
    if (failure.target === "embedding") {
      setAnswer({ field: "embedding", text: t(failure.key) });
      form.setError("embedding", { type: "server", message: "" });
      void queryClient.invalidateQueries({ queryKey: modelsKeyRoot(dataset.tenantId) });
      return;
    }
    setAlert(failure.text ?? t(failure.key, { workspace: workspaceName }));
  }

  async function onSubmit(submitted: DatasetFormValues): Promise<void> {
    if (inFlight.current) return;
    const changes = changesOf(dataset, submitted, locked);
    if (Object.keys(changes).length === 0) return;
    inFlight.current = true;
    pendingRef.current = true;
    setBusy(true);
    clearAnswers();
    try {
      await update.mutateAsync({ id: dataset.id, tenantId: dataset.tenantId, changes });
      notifySuccess(t("datasets.settings.saved"));
      onClose();
    } catch (error) {
      fail(error, submitted.name);
    } finally {
      inFlight.current = false;
      pendingRef.current = false;
      setBusy(false);
    }
  }

  return (
    <Form {...form}>
      <form data-testid="dataset-settings-form" noValidate aria-busy={busy || undefined} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <DialogHeader>
          <DialogTitle>{t("datasets.form.settingsTitle")}</DialogTitle>
          <DialogDescription>{t("datasets.form.settingsBody")}</DialogDescription>
        </DialogHeader>
        {alert === null ? null : <Alert data-testid="dataset-settings-error">{alert}</Alert>}
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("datasets.field.name")}</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  data-testid="field-dataset-name"
                  ref={(element) => {
                    field.ref(element);
                    nameInput.current = element;
                  }}
                  autoComplete="off"
                  onChange={(event) => {
                    clearAnswers("name");
                    field.onChange(event);
                  }}
                />
              </FormControl>
              <FormMessage />
              <ServerFieldError text={answer?.field === "name" ? answer.text : null} />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("datasets.field.description")}</FormLabel>
              <FormControl>
                <Textarea {...field} data-testid="field-dataset-description" maxLength={DESCRIPTION_MAX} />
              </FormControl>
              {values.description.length >= DESCRIPTION_COUNT_FROM ? (
                <p aria-live="polite" className="text-right text-xs font-normal tabular-nums text-muted-foreground">
                  {t("datasets.field.descriptionCount", { count: values.description.length })}
                </p>
              ) : null}
              <FormMessage />
            </FormItem>
          )}
        />
        {locked ? (
          <div className="flex flex-col gap-2">
            <p className="text-sm font-semibold leading-none">{t("datasets.field.embedding")}</p>
            <p data-testid="dataset-settings-embedding-fixed" className="break-words rounded-md border bg-muted px-3 py-2 text-sm font-normal">
              {modelName(dataset.embdId)}
            </p>
            <p className="text-sm font-normal text-muted-foreground">{t("datasets.field.embeddingFixed")}</p>
          </div>
        ) : (
          <FormField
            control={form.control}
            name="embedding"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t("datasets.field.embedding")}</FormLabel>
                <FormControl>
                  <LlmSelect
                    models={models}
                    type="embedding"
                    value={field.value}
                    disabled={busy}
                    data-testid="field-dataset-embedding"
                    onChange={(value) => {
                      clearAnswers("embedding");
                      field.onChange(value);
                    }}
                  />
                </FormControl>
                <FormDescription>{t("datasets.field.embeddingHelp")}</FormDescription>
                <FormMessage />
                <ServerFieldError text={answer?.field === "embedding" ? answer.text : null} />
              </FormItem>
            )}
          />
        )}
        <FormField
          control={form.control}
          name="permission"
          render={({ field }) => (
            <div data-testid="field-dataset-visibility" className="flex flex-col gap-2">
              <ChoiceGroup
                legend={t("datasets.field.visibility")}
                name="dataset-settings-visibility"
                value={field.value}
                disabled={busy}
                onChange={(value) => field.onChange(value)}
                options={[
                  { value: "me", title: t("datasets.visibility.meTitle"), description: t("datasets.visibility.meBody") },
                  { value: "team", title: t("datasets.visibility.teamTitle"), description: t("datasets.visibility.teamBody", { workspace: workspaceName }) },
                ]}
              />
              {narrowing ? (
                <p data-testid="dataset-settings-narrowing" className="flex items-start gap-1 text-xs font-normal text-muted-foreground">
                  <Info className="size-4 shrink-0" aria-hidden="true" />
                  <span>{t("datasets.visibility.narrowing")}</span>
                </p>
              ) : null}
            </div>
          )}
        />
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="ghost">
              {t("dialog.close")}
            </Button>
          </DialogClose>
          <Button
            type="submit"
            data-testid="dataset-settings-submit"
            aria-busy={busy || undefined}
            aria-disabled={busy || !changed ? true : undefined}
            className="aria-disabled:pointer-events-none aria-disabled:opacity-50"
          >
            {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
            {t("datasets.settings.submit")}
          </Button>
        </DialogFooter>
      </form>
    </Form>
  );
}
