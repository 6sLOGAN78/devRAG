import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent, type MutableRefObject } from "react";
import { useTranslation } from "react-i18next";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCreateChunkRequest, useUpdateChunkRequest } from "@/hooks/use-chunk-request";
import { useWorkspaceName } from "@/hooks/use-dataset-permissions";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import type { ChunkView } from "@/services/chunk-service";
import { notifySuccess } from "@/services/notify";
import { chunkFailureOf, type Placed } from "../dataset/errors";

/** Longest chunk text the form accepts. A guard only: the server refuses text over the embedding model's limit. */
export const MAX_CHUNK_TEXT = 32000;

export interface ChunkEditorProps {
  mode: "edit" | "add";
  datasetId: string;
  docId: string;
  /** Edit: the chunk as it was stored when the editor opened. */
  chunk?: ChunkView;
  /** Receives the textarea so the owner can return focus to it. */
  textareaRef?: MutableRefObject<HTMLTextAreaElement | null>;
  /** Runs a leaving action now, or holds it behind the Discard dialog while the text is changed. */
  guard: (action: () => void) => void;
  /** The typed text differs from the saved text. */
  onDirtyChange: (dirty: boolean) => void;
  /** The editor was discarded. */
  onClose: () => void;
  /** The write succeeded; the editor has nothing left to show. */
  onSaved: (chunk: ChunkView) => void;
}

interface Refusal {
  placed: Placed;
}

/**
 * The inline editor of one chunk, or of a new one (UI-17, CHUNK-19, CHUNK-20). A write is accepted only when the new text
 * could be embedded, so a refusal leaves the index as it was: the editor shows the reason, keeps the typed text and
 * stays open (D-11). Everything it holds (text, errors, the refusal) lives here, and the owner mounts one editor per
 * chunk, so nothing shows for another chunk (FE-04). The refusal is never a session event.
 */
export function ChunkEditor({ mode, datasetId, docId, chunk, textareaRef, guard, onDirtyChange, onClose, onSaved }: ChunkEditorProps) {
  const { t } = useTranslation();
  const adding = mode === "add";
  const saved = adding ? "" : (chunk?.text ?? "");
  const update = useUpdateChunkRequest();
  const create = useCreateChunkRequest();
  const workspaceName = useWorkspaceName(useActiveWorkspace()?.tenantId ?? "");
  const fieldId = useId();
  const messageId = useId();
  const field = useRef<HTMLTextAreaElement | null>(null);
  const alertRef = useRef<HTMLDivElement | null>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const [text, setText] = useState(saved);
  const [touched, setTouched] = useState(false);
  const [pending, setPending] = useState(false);
  const [refusal, setRefusal] = useState<Refusal | null>(null);

  const changed = text !== saved;
  const empty = text.trim() === "";
  const tooLong = text.length > MAX_CHUNK_TEXT;
  const valid = !empty && !tooLong;
  const canSave = changed && valid;
  const error = tooLong ? t("errors.chunkText.max") : touched && empty ? t("errors.chunkText.required") : null;

  const setField = useCallback(
    (element: HTMLTextAreaElement | null) => {
      field.current = element;
      if (textareaRef !== undefined) textareaRef.current = element;
    },
    [textareaRef],
  );

  useEffect(() => {
    mounted.current = true;
    const element = field.current;
    if (element !== null) {
      element.focus();
      element.setSelectionRange(element.value.length, element.value.length);
    }
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    onDirtyChange(changed);
  }, [changed, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);

  useEffect(() => {
    if (refusal !== null) alertRef.current?.focus();
  }, [refusal]);

  async function submit(): Promise<void> {
    if (inFlight.current) return;
    setTouched(true);
    if (!canSave) return;
    inFlight.current = true;
    setPending(true);
    setRefusal(null);
    try {
      const result = adding ? await create.mutateAsync({ datasetId, docId, content: text }) : await update.mutateAsync({ datasetId, docId, chunkId: chunk?.id ?? "", changes: { text } });
      notifySuccess(adding ? t("inspector.editor.added") : t("inspector.editor.saved"));
      onSaved(result);
    } catch (failure) {
      if (mounted.current) setRefusal({ placed: chunkFailureOf(failure, mode) });
    } finally {
      inFlight.current = false;
      if (mounted.current) setPending(false);
    }
  }

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      void submit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      if (!pending) guard(onClose);
    }
  }

  const reasonKey = refusal?.placed.key ?? null;
  const detail = refusal?.placed.detail;

  return (
    <div data-testid="chunk-editor" data-mode={mode} className="flex flex-col gap-3">
      {adding ? (
        <h2 data-testid="chunk-editor-heading" className="text-sm font-semibold">
          {t("inspector.editor.newHeading")}
        </h2>
      ) : null}
      <div className="flex flex-col gap-2">
        <Label htmlFor={fieldId}>{t("inspector.editor.label")}</Label>
        <Textarea
          id={fieldId}
          ref={setField}
          data-testid="chunk-editor-text"
          className="max-h-80 min-h-40 resize-y"
          value={text}
          readOnly={pending}
          aria-invalid={error !== null ? true : undefined}
          aria-describedby={error !== null ? `${messageId} ${fieldId}-help` : `${fieldId}-help`}
          onChange={(event) => setText(event.target.value)}
          onBlur={() => setTouched(true)}
          onKeyDown={keyDown}
        />
        {error !== null ? (
          <p id={messageId} data-testid="chunk-editor-error" className="text-xs font-normal text-destructive">
            {error}
          </p>
        ) : null}
        <p id={`${fieldId}-help`} className="text-xs font-normal text-muted-foreground">
          {adding ? t("inspector.editor.addHelp") : t("inspector.editor.editHelp")}
        </p>
      </div>
      {pending ? (
        <p role="status" data-testid="chunk-editor-saving" className="text-xs font-normal text-muted-foreground">
          {t("inspector.editor.saving")}
        </p>
      ) : null}
      {reasonKey !== null ? (
        <Alert ref={alertRef} tabIndex={-1} data-testid="chunk-editor-refusal" className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <div className="flex flex-col gap-1">
            <p className="font-semibold">{adding ? t("inspector.editor.refused.titleAdd") : t("inspector.editor.refused.titleEdit")}</p>
            <p>{t(reasonKey, { workspace: workspaceName })}</p>
            {detail !== undefined ? (
              <p data-testid="chunk-editor-detail" className="break-words text-xs text-muted-foreground">
                {detail}
              </p>
            ) : null}
            {adding ? null : <p>{t("inspector.editor.refused.unchanged")}</p>}
          </div>
        </Alert>
      ) : null}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button type="button" variant="ghost" data-testid="chunk-editor-discard" disabled={pending} onClick={onClose}>
          {t("inspector.editor.discard")}
        </Button>
        <Button
          type="button"
          data-testid="chunk-editor-save"
          aria-disabled={!canSave || pending ? true : undefined}
          aria-busy={pending || undefined}
          className="aria-disabled:pointer-events-none aria-disabled:opacity-50"
          onClick={() => void submit()}
        >
          {pending ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
          {adding ? t("inspector.list.add") : t("inspector.editor.save")}
        </Button>
      </div>
    </div>
  );
}
