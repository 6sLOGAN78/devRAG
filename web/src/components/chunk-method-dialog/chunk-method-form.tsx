import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useRef, useState, type MutableRefObject } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { ServerFieldError } from "@/components/create-dataset-dialog/server-field-error";
import { ParseConfiguration } from "@/components/parse-configuration";
import { fromEscaped, toEscaped } from "@/components/parse-configuration/delimiters";
import { chunkFormSchema, type ChunkFormInput, type ParseConfigField } from "@/components/parse-configuration/schema";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ChoiceGroup, type ChoiceOption } from "@/components/ui/choice-group";
import { DialogClose, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormField, FormItem } from "@/components/ui/form";
import { CHUNK_METHODS, GENERAL_METHOD, METHOD_STEMS, isChunkMethod, isImplemented } from "@/constants/chunk-methods";
import { SETTINGS_MODES, type SettingsMode } from "@/constants/failure-codes";
import { useWorkspaceName } from "@/hooks/use-dataset-permissions";
import { useUpdateDocumentSettingsRequest } from "@/hooks/use-document-request";
import { useUpdateDatasetChunkingRequest } from "@/hooks/use-knowledge-request";
import { invalidFieldOf, settingsFailureOf, storedUnavailableKey } from "@/pages/dataset/errors";
import { isCancelled } from "@/pages/datasets/errors";
import { notifySuccess } from "@/services/notify";

/** What a dialog edits: one document, or the dataset default. */
export type ChunkTarget =
  | { mode: typeof SETTINGS_MODES.document; datasetId: string; tenantId: string; documentId: string; name: string }
  | { mode: typeof SETTINGS_MODES.dataset; datasetId: string; tenantId: string; name: string };

/** The stored method and values the form starts from, whichever mode loaded them. */
export interface ChunkSettings {
  autoKeywords?: number;
  autoQuestions?: number;
  pages?: [number, number][];
  layoutRecognize?: boolean | string;
  resumeModel?: string;
  resumeUseModel?: boolean;
  asrModel?: string;
  audioLanguage?: string;
  imageModel?: string;
  pictureOcrOnly?: boolean;
  parserId: string;
  chunkTokenNum: number;
  delimiter: string;
  overlappedPercent: number;
  /** Chunks the document holds; 0 in the dataset mode. */
  chunkCount: number;
  /** Parse state of the document; "0" in the dataset mode. */
  run: string;
}

export interface ChunkMethodFormProps {
  target: ChunkTarget;
  settings: ChunkSettings;
  /** True while a save is in flight: the dialog then ignores Esc and outside clicks. */
  pendingRef: MutableRefObject<boolean>;
  onClose: () => void;
}

type Changes = {autoKeywords?:number;autoQuestions?:number;resumeModel?:string;resumeUseModel?:boolean;asrModel?:string;audioLanguage?:string;imageModel?:string;pictureOcrOnly?:boolean; parserId?: string; chunkTokenNum?: number; delimiter?: string; overlappedPercent?: number; pages?: [number, number][]; layoutRecognize?: boolean | string };

/** The keys whose value differs from the stored one: exactly what the request carries. Layout and keywords are never among them. */
function changesOf(settings: ChunkSettings, method: string, values: { chunkSize: number; delimiters: string; overlap: number; pageRanges: [number, number][]; layoutRecognize: boolean | string; autoKeywords:number;autoQuestions:number;resumeModel?:string;resumeUseModel?:boolean;asrModel?:string;audioLanguage?:string;imageModel?:string;pictureOcrOnly?:boolean }): Changes {
  const changes: Changes = {};
  if (values.autoKeywords !== (settings.autoKeywords ?? 0)) changes.autoKeywords=values.autoKeywords;
  if (values.autoQuestions !== (settings.autoQuestions ?? 0)) changes.autoQuestions=values.autoQuestions;
  if ((values.resumeModel ?? "") !== (settings.resumeModel ?? "")) changes.resumeModel=values.resumeModel ?? "";
  if ((values.resumeUseModel ?? false) !== (settings.resumeUseModel ?? false)) changes.resumeUseModel=values.resumeUseModel ?? false;
  if ((values.asrModel ?? "") !== (settings.asrModel ?? "")) changes.asrModel=values.asrModel ?? "";
  if ((values.audioLanguage ?? "") !== (settings.audioLanguage ?? "")) changes.audioLanguage=values.audioLanguage ?? "";
  if ((values.imageModel ?? "") !== (settings.imageModel ?? "")) changes.imageModel=values.imageModel ?? "";
  if ((values.pictureOcrOnly ?? false) !== (settings.pictureOcrOnly ?? false)) changes.pictureOcrOnly=values.pictureOcrOnly ?? false;
  if (isImplemented(method) && method !== settings.parserId) changes.parserId = method;
  if (values.chunkSize !== settings.chunkTokenNum) changes.chunkTokenNum = values.chunkSize;
  if (values.delimiters !== settings.delimiter) changes.delimiter = values.delimiters;
  if (values.overlap !== settings.overlappedPercent) changes.overlappedPercent = values.overlap;
  if (JSON.stringify(values.pageRanges) !== JSON.stringify(settings.pages ?? [])) changes.pages = values.pageRanges;
  if (values.layoutRecognize !== (settings.layoutRecognize ?? true)) changes.layoutRecognize = values.layoutRecognize;
  return changes;
}

const FIELD_NAMES = ["chunkSize", "delimiters", "overlap", "pageRanges", "layoutRecognize", "autoKeywords", "autoQuestions", "imageModel", "pictureOcrOnly", "asrModel", "audioLanguage", "resumeModel", "resumeUseModel"] as const satisfies readonly ParseConfigField[];

/**
 * The form of the chunking dialog: the method group (only General can be chosen), the settings of General and the
 * footer. Only changed keys are sent; the settings of a parsed document are saved without re-chunking anything. Server
 * refusals are placed by status and reason. The body is mounted only while the dialog is open and keyed by its target.
 */
export function ChunkMethodForm({ target, settings, pendingRef, onClose }: ChunkMethodFormProps) {
  const { t } = useTranslation();
  const mode: SettingsMode = target.mode;
  const workspaceName = useWorkspaceName(target.tenantId);
  const updateDocument = useUpdateDocumentSettingsRequest();
  const updateDataset = useUpdateDatasetChunkingRequest();
  const stored = settings.parserId === "" ? GENERAL_METHOD : settings.parserId;
  const storedUnavailable = !isImplemented(stored);
  const form = useForm<ChunkFormInput>({
    resolver: zodResolver(chunkFormSchema, undefined, { raw: true }),
    mode: "onSubmit",
    reValidateMode: "onChange",
    defaultValues: {
      method: storedUnavailable ? "" : stored,
      chunkSize: String(settings.chunkTokenNum),
      delimiters: toEscaped(settings.delimiter),
      overlap: String(settings.overlappedPercent),
      layoutRecognize: settings.layoutRecognize ?? true,
      resumeModel:settings.resumeModel ?? "",
      resumeUseModel:settings.resumeUseModel ?? false,
      autoKeywords:String(settings.autoKeywords ?? 0),
      autoQuestions:String(settings.autoQuestions ?? 0),
      asrModel:settings.asrModel ?? "",
      audioLanguage:settings.audioLanguage ?? "",
      imageModel:settings.imageModel ?? "",
      pictureOcrOnly:settings.pictureOcrOnly ?? false,
      pageRanges: (settings.pages ?? []).map(([start, end]) => start === end ? String(start) : `${start}-${end}`).join(", "),
    },
  });
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState<string | null>(null);
  const [methodAnswer, setMethodAnswer] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Partial<Record<ParseConfigField, string>>>({});
  const values = form.watch();
  const parsed = chunkFormSchema.safeParse(values);
  const changes = parsed.success ? changesOf(settings, parsed.data.method, parsed.data) : {};
  const changed = Object.keys(changes).length > 0;
  const canSave = parsed.success && isImplemented(parsed.data.method) && changed;
  const parsedBefore = target.mode === SETTINGS_MODES.document && (settings.chunkCount > 0 || settings.run !== "0");

  function clearAnswers(field?: ParseConfigField): void {
    setAlert(null);
    if (field === undefined) {
      setMethodAnswer(null);
      setAnswers({});
    } else {
      setAnswers((current) => {
        if (current[field] === undefined) return current;
        const { [field]: _removed, ...rest } = current;
        return rest;
      });
    }
  }

  function fieldMessage(field: ParseConfigField): string {
    if (field === "layoutRecognize") return t("errors.chunking.layout");
    if (field === "pageRanges") return t("errors.chunking.pagesRange");
    if (field === "chunkSize") return t("errors.chunking.sizeRange");
    if (field === "autoKeywords") return t("errors.chunking.keywordRange");
    if (field === "autoQuestions") return t("errors.chunking.questionRange");
    if (field === "overlap") return t("errors.chunking.overlapRange");
    return [...fromEscaped(form.getValues("delimiters"))].length === 0 ? t("errors.chunking.delimitersRequired") : t("errors.chunking.delimitersMax");
  }

  function fail(error: unknown): void {
    if (isCancelled(error)) return;
    const field = invalidFieldOf(error);
    if (field !== null) {
      setAnswers({ [field]: fieldMessage(field) });
      form.setFocus(field);
      return;
    }
    const failure = settingsFailureOf(error, mode);
    if (failure.key === "datasets.chunking.error.method") {
      setMethodAnswer(t(failure.key));
      return;
    }
    setAlert(t(failure.key ?? "datasets.chunking.error.fallback", { workspace: workspaceName }));
  }

  async function onSubmit(raw: ChunkFormInput): Promise<void> {
    if (inFlight.current) return;
    const result = chunkFormSchema.safeParse(raw);
    if (!result.success || !isImplemented(result.data.method)) return;
    const pending = changesOf(settings, result.data.method, result.data);
    if (Object.keys(pending).length === 0) return;
    inFlight.current = true;
    pendingRef.current = true;
    setBusy(true);
    clearAnswers();
    try {
      if (target.mode === SETTINGS_MODES.document) await updateDocument.mutateAsync({ datasetId: target.datasetId, docId: target.documentId, changes: pending });
      else await updateDataset.mutateAsync({ id: target.datasetId, tenantId: target.tenantId, changes: pending });
      notifySuccess(t("datasets.chunking.saved"));
      onClose();
    } catch (error) {
      fail(error);
    } finally {
      inFlight.current = false;
      pendingRef.current = false;
      setBusy(false);
    }
  }

  const options: ChoiceOption[] = CHUNK_METHODS.map((id) => {
    const stem = METHOD_STEMS[id];
    const later = !isImplemented(id);
    return {
      value: id,
      title: t(`datasets.chunking.method.${stem}.title`),
      description: t(`datasets.chunking.method.${stem}.body`),
      disabled: later,
      badge: later ? t("datasets.chunking.later") : undefined,
      testId: `chunk-method-option-${id}`,
    };
  });
  const storedName = isChunkMethod(stored) ? t(`datasets.chunking.method.${METHOD_STEMS[stored]}.title`) : stored;

  return (
    <Form {...form}>
      <form data-testid="chunk-method-form" noValidate aria-busy={busy || undefined} onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <DialogHeader>
          <DialogTitle>{target.mode === SETTINGS_MODES.document ? t("datasets.chunking.titleDocument", { name: target.name }) : t("datasets.chunking.titleDataset")}</DialogTitle>
          <DialogDescription>{target.mode === SETTINGS_MODES.document ? t("datasets.chunking.bodyDocument") : t("datasets.chunking.bodyDataset")}</DialogDescription>
        </DialogHeader>
        {parsedBefore ? (
          <Alert variant="info" data-testid="chunk-method-parsed-note">
            {t("datasets.chunking.parsedNote", { count: settings.chunkCount })}
          </Alert>
        ) : null}
        {alert === null ? null : <Alert data-testid="chunk-method-error">{alert}</Alert>}
        {storedUnavailable ? (
          <Alert variant="info" data-testid="chunk-method-unavailable">
            {t(storedUnavailableKey(mode), { method: storedName })}
          </Alert>
        ) : null}
        <FormField
          control={form.control}
          name="method"
          render={({ field }) => (
            <FormItem data-testid="chunk-method-group">
              <ChoiceGroup
                legend={t("datasets.chunking.method.legend")}
                help={t("datasets.chunking.method.help")}
                name="chunk-method"
                value={field.value}
                disabled={busy}
                options={options}
                onChange={(value) => {
                  setMethodAnswer(null);
                  setAlert(null);
                  field.onChange(value);
                }}
              />
              <ServerFieldError text={methodAnswer} />
            </FormItem>
          )}
        />
        <ParseConfiguration control={form.control} tag={form.watch("method") === "tag"} resume={form.watch("method") === "resume"} wholeDocument={form.watch("method") === "one"} questionAnswer={form.watch("method") === "qa"} book={form.watch("method") === "book"} paper={form.watch("method") === "paper"} laws={form.watch("method") === "laws"} presentation={form.watch("method") === "presentation"} table={form.watch("method") === "table"} email={form.watch("method") === "email"} audio={form.watch("method") === "audio"} picture={form.watch("method") === "picture"} disabled={busy} answers={answers} onEdit={(field) => clearAnswers(FIELD_NAMES.find((name) => name === field))} />
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="ghost">
              {t("dialog.close")}
            </Button>
          </DialogClose>
          <Button
            type="submit"
            data-testid="chunk-method-submit"
            aria-busy={busy || undefined}
            aria-disabled={busy || !canSave ? true : undefined}
            className={changed ? "aria-disabled:opacity-50" : "aria-disabled:pointer-events-none aria-disabled:opacity-50"}
          >
            {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
            {t("datasets.settings.submit")}
          </Button>
        </DialogFooter>
      </form>
    </Form>
  );
}
