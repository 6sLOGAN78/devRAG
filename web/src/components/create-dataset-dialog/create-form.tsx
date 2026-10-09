import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { LlmSelect } from "@/components/llm-select";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ChoiceGroup } from "@/components/ui/choice-group";
import { DialogClose, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { datasetFilesPath } from "@/constants/app-paths";
import { useCreateDatasetRequest } from "@/hooks/use-knowledge-request";
import { modelsKeyRoot } from "@/hooks/use-llm-request";
import { datasetErrorTarget, isCancelled } from "@/pages/datasets/errors";
import { notifySuccess } from "@/services/notify";
import type { ModelView } from "@/services/model-service";
import { DESCRIPTION_COUNT_FROM, DESCRIPTION_MAX, datasetSchema, type DatasetFormValues } from "./schemas";
import { ServerFieldError } from "./server-field-error";

interface CreateFormProps {
  tenantId: string;
  workspaceName: string;
  /** The workspace's embedding models, live: a refetch after a refusal updates the select. */
  models: readonly ModelView[];
  /** The workspace default embedding model, preselected (an explicit owner or admin choice, so not a guess). */
  defaultEmbedding: string;
  /** True while a create call is in flight: the dialog then ignores Esc and outside clicks. */
  pendingRef: MutableRefObject<boolean>;
  onClose: () => void;
  /** The server says there is no default embedding model after all. */
  onBlocked: () => void;
}

type FieldAnswer = { field: "name" | "embedding"; text: string };

/**
 * The normal create form: name, description, embedding model and who can see it. The visibility defaults to "Only me"
 * (D-08). The SPA sends no parser (the server applies the documented default). Server refusals are placed by
 * `datasetErrorTarget`; a second submit while one is in flight is ignored.
 */
export function CreateForm({ tenantId, workspaceName, models, defaultEmbedding, pendingRef, onClose, onBlocked }: CreateFormProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const create = useCreateDatasetRequest();
  const form = useForm<DatasetFormValues>({
    resolver: zodResolver(datasetSchema),
    mode: "onSubmit",
    reValidateMode: "onChange",
    defaultValues: { name: "", description: "", embedding: defaultEmbedding, permission: "me" },
  });
  const nameInput = useRef<HTMLInputElement | null>(null);
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState<string | null>(null);
  const [answer, setAnswer] = useState<FieldAnswer | null>(null);
  const description = form.watch("description");

  useEffect(() => {
    nameInput.current?.focus();
  }, []);

  // A model that disappeared from the list (a refusal refetched it) must not stay selected unseen.
  useEffect(() => {
    const chosen = form.getValues("embedding");
    if (chosen !== "" && !models.some((model) => model.id === chosen && model.type === "embedding")) form.setValue("embedding", "");
  }, [models, form]);

  function clearAnswers(field?: FieldAnswer["field"]): void {
    setAlert(null);
    setAnswer((current) => (field === undefined || current?.field === field ? null : current));
  }

  function fail(error: unknown, name: string): void {
    if (isCancelled(error)) return;
    const failure = datasetErrorTarget(error);
    if (failure.target === "blocked") {
      onBlocked();
      return;
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
      void queryClient.invalidateQueries({ queryKey: modelsKeyRoot(tenantId) });
      return;
    }
    setAlert(failure.text ?? t(failure.key, { workspace: workspaceName }));
  }

  async function onSubmit(values: DatasetFormValues): Promise<void> {
    if (inFlight.current) return;
    inFlight.current = true;
    pendingRef.current = true;
    setBusy(true);
    clearAnswers();
    const text = values.description.trim();
    try {
      const created = await create.mutateAsync({
        tenantId,
        name: values.name,
        embdId: values.embedding,
        permission: values.permission,
        ...(text === "" ? {} : { description: text }),
      });
      notifySuccess(t("datasets.created"));
      onClose();
      if (created.id !== "") navigate(datasetFilesPath(created.id));
    } catch (error) {
      fail(error, values.name);
    } finally {
      inFlight.current = false;
      pendingRef.current = false;
      setBusy(false);
    }
  }

  return (
    <Form {...form}>
      <form data-testid="create-dataset-form" noValidate aria-busy={busy || undefined} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <DialogHeader>
          <DialogTitle>{t("datasets.form.createTitle")}</DialogTitle>
          <DialogDescription>{t("datasets.form.createBody")}</DialogDescription>
        </DialogHeader>
        {alert === null ? null : <Alert data-testid="create-dataset-error">{alert}</Alert>}
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
              {description.length >= DESCRIPTION_COUNT_FROM ? (
                <p aria-live="polite" className="text-right text-xs font-normal tabular-nums text-muted-foreground">
                  {t("datasets.field.descriptionCount", { count: description.length })}
                </p>
              ) : null}
              <FormMessage />
            </FormItem>
          )}
        />
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
        <FormField
          control={form.control}
          name="permission"
          render={({ field }) => (
            <div data-testid="field-dataset-visibility">
              <ChoiceGroup
                legend={t("datasets.field.visibility")}
                name="dataset-visibility"
                value={field.value}
                disabled={busy}
                onChange={(value) => field.onChange(value)}
                options={[
                  { value: "me", title: t("datasets.visibility.meTitle"), description: t("datasets.visibility.meBody") },
                  { value: "team", title: t("datasets.visibility.teamTitle"), description: t("datasets.visibility.teamBody", { workspace: workspaceName }) },
                ]}
              />
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
            data-testid="create-dataset-submit"
            aria-busy={busy || undefined}
            aria-disabled={busy || undefined}
            className="aria-disabled:pointer-events-none aria-disabled:opacity-50"
          >
            {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
            {t("datasets.create")}
          </Button>
        </DialogFooter>
      </form>
    </Form>
  );
}
