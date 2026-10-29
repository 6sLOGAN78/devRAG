import { Loader2 } from "lucide-react";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { ErrorState } from "@/components/error-state";
import { LlmSelect } from "@/components/llm-select";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { useDefaultsRequest, useModelsRequest, useModelTenantId, useSaveDefaultsRequest } from "@/hooks/use-llm-request";
import { ApiError } from "@/services/http";
import { notifySuccess } from "@/services/notify";
import type { DefaultsChanges, DefaultsView, ModelView } from "@/services/model-service";

const MAX_SERVER_MESSAGE = 300;

interface DefaultsValues {
  chat: string;
  embedding: string;
  vision:string;
}

function DefaultsSkeleton() {
  const { t } = useTranslation();
  return (
    <div data-testid="defaults-skeleton" className="flex max-w-md flex-col gap-4">
      <p role="status" className="sr-only">
        {t("models.defaults.loading")}
      </p>
      <Skeleton className="h-10 w-full" aria-hidden="true" />
      <Skeleton className="h-10 w-full" aria-hidden="true" />
    </div>
  );
}

/** A saved default counts only while its model still exists in the workspace; otherwise the select shows "Not set". */
function existing(id: string, models: readonly ModelView[]): string {
  return models.some((model) => model.id === id) ? id : "";
}

/**
 * The server's own sentence for a refusal of the chosen ids (400, 404, 409: the model is gone or not usable), bounded and
 * shown as text; every other failure has fixed copy.
 */
function failureText(error: unknown, fallback: string): string {
  if (error instanceof ApiError && (error.status === 400 || error.status === 404 || error.status === 409)) {
    const message = error.message.trim();
    if (message !== "" && message.length <= MAX_SERVER_MESSAGE) return message;
  }
  return fallback;
}

interface FormProps {
  tenantId: string;
  chatModels: readonly ModelView[];
  embeddingModels: readonly ModelView[];
  visionModels: readonly ModelView[];
  saved: DefaultsView;
}

/**
 * The owner and admin form. Initial values come only from the saved defaults, and only while their model still exists:
 * nothing is preselected or guessed (D-18). The parent remounts the form (by `key`) whenever the effective saved values
 * change, so a successful save, a deleted provider or another admin's change all reset the dirty state.
 */
function DefaultsForm({ tenantId, chatModels, embeddingModels, visionModels, saved }: FormProps) {
  const { t } = useTranslation();
  const save = useSaveDefaultsRequest();
  const baseline = useRef<DefaultsValues>({ chat: existing(saved.chat, chatModels), embedding: existing(saved.embedding, embeddingModels),vision:existing(saved.vision ?? "",visionModels) });
  const form = useForm<DefaultsValues>({ mode: "onSubmit", defaultValues: baseline.current });
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = form.formState.isDirty;

  async function onSubmit(values: DefaultsValues): Promise<void> {
    if (inFlight.current) return;
    const changes: DefaultsChanges = {};
    if (values.chat !== baseline.current.chat) changes.chat = values.chat === "" ? null : values.chat;
    if (values.embedding !== baseline.current.embedding) changes.embedding = values.embedding === "" ? null : values.embedding;
    if(values.vision !== baseline.current.vision) changes.vision=values.vision === "" ? null : values.vision;
    if (Object.keys(changes).length === 0) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      await save.mutateAsync({ tenantId, changes });
      baseline.current = values;
      form.reset(values);
      notifySuccess(t("models.defaults.saved"));
    } catch (failure) {
      setError(failureText(failure, t("models.defaults.failed")));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <Form {...form}>
      <form data-testid="defaults-form" noValidate aria-busy={busy || undefined} onSubmit={form.handleSubmit(onSubmit)} className="flex max-w-md flex-col gap-4">
        {error === null ? null : <Alert data-testid="defaults-error">{error}</Alert>}
        <FormField
          control={form.control}
          name="chat"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("models.defaults.chat")}</FormLabel>
              <FormControl>
                <LlmSelect
                  models={chatModels}
                  type="chat"
                  value={field.value}
                  disabled={chatModels.length === 0 || busy}
                  data-testid="default-chat"
                  onChange={(value) => {
                    setError(null);
                    field.onChange(value);
                  }}
                />
              </FormControl>
              {chatModels.length === 0 ? <FormDescription>{t("models.defaults.noChat")}</FormDescription> : null}
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="embedding"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("models.defaults.embedding")}</FormLabel>
              <FormControl>
                <LlmSelect
                  models={embeddingModels}
                  type="embedding"
                  value={field.value}
                  disabled={embeddingModels.length === 0 || busy}
                  data-testid="default-embedding"
                  onChange={(value) => {
                    setError(null);
                    field.onChange(value);
                  }}
                />
              </FormControl>
              <FormDescription>{embeddingModels.length === 0 ? t("models.defaults.noEmbedding") : t("models.defaults.embeddingHelp")}</FormDescription>
            </FormItem>
          )}
        />
        {visionModels.length > 0 ? <FormField control={form.control} name="vision" render={({field})=><FormItem><FormLabel>{t("models.defaults.vision")}</FormLabel><FormControl><LlmSelect models={visionModels} type="vision" value={field.value} disabled={busy} data-testid="default-vision" onChange={value=>{setError(null);field.onChange(value);}}/></FormControl></FormItem>}/> : null}
        <div>
          <Button
            type="submit"
            data-testid="defaults-submit"
            aria-busy={busy || undefined}
            aria-disabled={!dirty || busy ? true : undefined}
            className="aria-disabled:pointer-events-none aria-disabled:opacity-50"
          >
            {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
            {t("models.defaults.submit")}
          </Button>
        </div>
      </form>
    </Form>
  );
}

/** Loads the two model lists the selects need and mounts the form when both are in. Only owners and admins reach this. */
function DefaultsEditor({ saved }: { saved: DefaultsView }) {
  const { t } = useTranslation();
  const tenantId = useModelTenantId();
  const chat = useModelsRequest("chat");
  const embedding = useModelsRequest("embedding");
  const vision = useModelsRequest("vision",saved.vision !== undefined);
  if (chat.isPending || embedding.isPending || (saved.vision !== undefined && vision.isPending)) return <DefaultsSkeleton />;
  if (chat.isError || embedding.isError || (saved.vision !== undefined && vision.isError) || chat.data === undefined || embedding.data === undefined || tenantId === null) {
    return (
      <ErrorState
        noun={t("models.errorNoun.defaults")}
        onAction={() => {
          void chat.refetch();
          void embedding.refetch();
          if(saved.vision !== undefined) void vision.refetch();
        }}
      />
    );
  }
  const formKey = `${tenantId}|${existing(saved.chat, chat.data)}|${existing(saved.embedding, embedding.data)}|${existing(saved.vision ?? "",vision.data ?? [])}`;
  return <DefaultsForm key={formKey} tenantId={tenantId} chatModels={chat.data} embeddingModels={embedding.data} visionModels={vision.data ?? []} saved={saved} />;
}

/** Members read the defaults as plain text: a definition list, no select and no button (D-07). */
function DefaultsReadOnly({ saved }: { saved: DefaultsView }) {
  const { t } = useTranslation();
  const rows = [
    ...(saved.vision ? [{label:t("models.defaults.vision"),value:saved.vision}] : []),
    { label: t("models.defaults.chat"), value: saved.chat },
    { label: t("models.defaults.embedding"), value: saved.embedding },
  ];
  return (
    <dl data-testid="defaults-readonly" className="grid max-w-md grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-[auto_1fr]">
      {rows.map((row) => (
        <div key={row.label} className="contents">
          <dt className="font-semibold">{row.label}</dt>
          {row.value === "" ? <dd className="font-normal text-muted-foreground">{t("common.notSet")}</dd> : <dd className="break-all font-mono">{row.value}</dd>}
        </div>
      ))}
    </dl>
  );
}

/**
 * Default models (UI-37, TEN-12, D-18). Owners and admins choose the default chat and embedding model from the models the
 * workspace has configured; both stay on "Not set" until someone chooses. Members see the same two values read-only.
 * Loading and failure are this card's own, independent of the providers card. The server decides who may write.
 */
export function DefaultsCard({ role }: { role: string | undefined }) {
  const { t } = useTranslation();
  const defaults = useDefaultsRequest();
  const elevated = role === "owner" || role === "admin";
  let body;
  if (defaults.isPending) {
    body = <DefaultsSkeleton />;
  } else if (defaults.isError) {
    body = <ErrorState noun={t("models.errorNoun.defaults")} onAction={() => void defaults.refetch()} />;
  } else if (elevated) {
    body = <DefaultsEditor saved={defaults.data} />;
  } else {
    body = <DefaultsReadOnly saved={defaults.data} />;
  }
  return (
    <Card data-testid="defaults-card">
      <CardHeader>
        <CardTitle>{t("models.defaults.title")}</CardTitle>
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  );
}
