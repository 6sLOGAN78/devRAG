import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useInvalidateDocuments } from "@/hooks/use-document-request";
import type { UploadLimitsView } from "@/services/dataset-service";
import { uploadDocument } from "@/services/document-service";
import { Dropzone, carriesFiles, type DroppedEntry } from "./dropzone";
import { applyBatchLimits, checkFile, fileKey, formatBytes, resolveUploadLimits } from "./file-rules";
import { createQueueStore, queueCounts, runQueue, type NewEntry } from "./upload-queue";
import { StopUploadsDialog } from "./stop-dialog";
import { UploadRow } from "./upload-row";

/** What the dialog needs to know about the dataset it uploads into. */
export interface UploadDataset {
  id: string;
  name: string;
  /** Documents the dataset holds now (from the dataset detail). */
  docNum: number;
}

export interface FileUploadDialogProps {
  dataset: UploadDataset;
  /** `uploadLimits` of the dataset detail; null falls back to the server's defaults. */
  limits: UploadLimitsView | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Files already dropped on the page behind the dialog; queued as soon as it opens. */
  initialFiles?: File[];
  /** Where focus goes when the dialog has closed. There is no trigger inside it, so the owner decides. */
  onCloseAutoFocus?: (event: Event) => void;
}

interface BatchNotice {
  tooMany: number;
  datasetFull: number;
  /** Documents the dataset would hold, counting files waiting to upload. */
  current: number;
}

/**
 * The upload dialog (UI-12). Mounted only while open, so every opening starts with an empty list and a fresh queue.
 * It never closes by itself: rename notices and failures stay visible until the user says "Done" or "Close".
 */
export function FileUploadDialog(props: FileUploadDialogProps) {
  return props.open ? <UploadSession {...props} /> : null;
}

function UploadSession({ dataset, limits: limitsView, onOpenChange, initialFiles, onCloseAutoFocus }: FileUploadDialogProps) {
  const { t, i18n } = useTranslation();
  const limits = useMemo(() => resolveUploadLimits(limitsView), [limitsView]);
  const invalidate = useInvalidateDocuments();
  const invalidateRef = useRef(invalidate);
  invalidateRef.current = invalidate;

  const [store] = useState(() => createQueueStore());
  const state = useSyncExternalStore(store.subscribe, store.getState);
  const [runner] = useState(() =>
    runQueue({
      getState: store.getState,
      dispatch: store.dispatch,
      upload: (file, call) => uploadDocument(dataset.id, file, call),
      // A cancelled request may still have stored the file, so it refreshes the list too.
      onSettled: (outcome) => {
        if (outcome !== "failed") invalidateRef.current(dataset.id);
      },
    }),
  );
  const counts = queueCounts(state);

  const [notice, setNotice] = useState<BatchNotice | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [confirmStop, setConfirmStop] = useState(false);
  const chooseRef = useRef<HTMLButtonElement>(null);
  const submitRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const pendingFocus = useRef<number | "choose" | null>(null);

  const datasetFull = dataset.docNum >= limits.maxDocuments;
  const busy = counts.pending > 0;
  const finished = !busy && counts.ready === 0 && counts.settled > 0;
  const accept = limits.allowedExtensions.map((ext) => `.${ext}`).join(",");

  function addFiles(entries: DroppedEntry[]): void {
    const current = store.getState();
    const known = new Set(current.rows.map((row) => row.key));
    const fresh: DroppedEntry[] = [];
    for (const entry of entries) {
      const key = fileKey(entry.file);
      if (known.has(key)) continue;
      known.add(key);
      fresh.push(entry);
    }
    if (fresh.length === 0) return;

    const verdicts = fresh.map((entry) => ({ entry, check: checkFile(entry.file, limits, limits.allowedExtensions, { isDirectory: entry.isDirectory }) }));
    const passing = verdicts.filter((verdict) => verdict.check.ok).map((verdict) => verdict.entry.file);
    const before = queueCounts(current);
    const waiting = before.ready + before.uploading;
    const batch = applyBatchLimits(passing, new Set(), {
      maxFiles: limits.maxFilesPerRequest - before.ready,
      remaining: limits.maxDocuments - dataset.docNum - waiting,
    });
    const accepted = new Set(batch.accepted);
    const added: NewEntry[] = [];
    let refused = 0;
    for (const { entry, check } of verdicts) {
      if (!check.ok) {
        added.push({ file: entry.file, rejection: check.reason });
        refused += 1;
      } else if (accepted.has(entry.file)) added.push({ file: entry.file, rejection: null });
    }
    store.dispatch({ type: "add", entries: added });

    setNotice(batch.tooMany + batch.datasetFull > 0 ? { tooMany: batch.tooMany, datasetFull: batch.datasetFull, current: dataset.docNum + waiting } : null);
    const notAdded = refused + batch.tooMany + batch.datasetFull;
    const parts: string[] = [];
    if (batch.accepted.length > 0) parts.push(t("upload.live.added", { count: batch.accepted.length }));
    if (notAdded > 0) parts.push(t("upload.live.tooMany", { count: notAdded }));
    setAnnouncement(parts.join(". "));
  }

  const addFilesRef = useRef(addFiles);
  addFilesRef.current = addFiles;
  useEffect(() => {
    if (initialFiles && initialFiles.length > 0) addFilesRef.current(initialFiles.map((file) => ({ file, isDirectory: false })));
    // Only the files present at opening are queued; later changes of the prop do nothing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A drop that misses the zone must not make the browser open the file (T-03-24-05).
  useEffect(() => {
    const prevent = (event: Event) => {
      if (carriesFiles((event as DragEvent).dataTransfer)) event.preventDefault();
    };
    window.addEventListener("dragover", prevent);
    window.addEventListener("drop", prevent);
    return () => {
      window.removeEventListener("dragover", prevent);
      window.removeEventListener("drop", prevent);
    };
  }, []);

  // Leaving the page or closing the dialog never leaves a request running unseen.
  useEffect(() => () => runner.stop(), [runner]);

  // End of a batch: say how it went and move focus to "Done".
  const wasBusy = useRef(false);
  useEffect(() => {
    if (busy) {
      wasBusy.current = true;
      return;
    }
    if (!wasBusy.current) return;
    wasBusy.current = false;
    setAnnouncement(t("upload.live.summary", { done: counts.done, failed: counts.failed }));
    if (counts.ready === 0 && !confirmStop) submitRef.current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy, counts.done, counts.failed, counts.ready]);

  // After a row is removed, focus goes to the next row's action, or back to "Choose files".
  useEffect(() => {
    const target = pendingFocus.current;
    if (target === null) return;
    pendingFocus.current = null;
    if (target === "choose") {
      chooseRef.current?.focus();
      return;
    }
    listRef.current?.querySelector<HTMLElement>(`[data-row-id="${target}"] [data-row-action]`)?.focus();
  }, [state.rows]);

  function removeRow(id: number): void {
    const rows = store.getState().rows;
    const index = rows.findIndex((row) => row.id === id);
    const neighbour = rows[index + 1] ?? rows[index - 1];
    pendingFocus.current = neighbour ? neighbour.id : "choose";
    store.dispatch({ type: "remove", id });
  }

  function requestClose(): void {
    if (counts.pending > 0) setConfirmStop(true);
    else onOpenChange(false);
  }

  function stopUploads(): void {
    runner.stop();
    setConfirmStop(false);
    onOpenChange(false);
  }

  function submit(): void {
    if (finished) {
      onOpenChange(false);
      return;
    }
    if (busy || counts.ready === 0) return;
    setAnnouncement(t("upload.live.started", { count: counts.ready }));
    runner.start();
  }

  const language = i18n.language;
  const submitLabel = finished ? t("upload.done") : busy ? t("upload.submitting", { done: counts.queuedSettled, total: counts.queued }) : t("upload.submit", { count: counts.ready });
  const title = t("upload.title", { dataset: dataset.name });

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) requestClose();
      }}
    >
      <DialogContent
        className="max-w-xl"
        data-testid="upload-dialog"
        onCloseAutoFocus={onCloseAutoFocus}
        onOpenAutoFocus={(event) => {
          if (chooseRef.current) {
            event.preventDefault();
            chooseRef.current.focus();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle className="break-words pr-6">{title}</DialogTitle>
          <DialogDescription>{t("upload.description", { size: formatBytes(limits.maxFileBytes, language), maxFiles: limits.maxFilesPerRequest })}</DialogDescription>
        </DialogHeader>

        {datasetFull ? (
          <Alert variant="info" data-testid="upload-full">
            {t("upload.full", { max: limits.maxDocuments })}
          </Alert>
        ) : (
          <Dropzone accept={accept} label={title} chooseRef={chooseRef} onFiles={addFiles} />
        )}

        {state.fatal !== null ? (
          <Alert data-testid="upload-fatal">{state.fatal === "gone" ? t("upload.error.gone") : t("upload.error.forbidden")}</Alert>
        ) : null}
        {notice !== null ? (
          <Alert variant="info" data-testid="upload-batch-notice">
            {notice.tooMany > 0 ? <p>{t("upload.batch.tooMany", { max: limits.maxFilesPerRequest, count: notice.tooMany })}</p> : null}
            {notice.datasetFull > 0 ? <p>{t("upload.batch.datasetFull", { max: limits.maxDocuments, current: notice.current, count: notice.datasetFull })}</p> : null}
          </Alert>
        ) : null}
        {counts.renamed > 0 ? (
          <Alert variant="info" data-testid="upload-rename-notice">
            {t("upload.renamed", { count: counts.renamed })}
          </Alert>
        ) : null}

        {state.rows.length > 0 ? (
          <ul ref={listRef} data-testid="upload-list" className="max-h-80 divide-y overflow-y-auto">
            {state.rows.map((row) => (
              <UploadRow key={row.id} row={row} maxFileBytes={limits.maxFileBytes} onRemove={removeRow} onCancel={runner.cancel} onRetry={runner.retry} />
            ))}
          </ul>
        ) : null}

        <div role="status" aria-live="polite" className="sr-only" data-testid="upload-live">
          {announcement}
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" data-testid="upload-close" onClick={requestClose}>
            {t("dialog.close")}
          </Button>
          <Button
            type="button"
            ref={submitRef}
            data-testid="upload-submit"
            aria-label={finished ? t("upload.closeDialog") : undefined}
            aria-disabled={!finished && (busy || counts.ready === 0) ? true : undefined}
            aria-busy={busy ? true : undefined}
            className="aria-disabled:cursor-not-allowed aria-disabled:opacity-50"
            onClick={submit}
          >
            {submitLabel}
          </Button>
        </DialogFooter>
        <StopUploadsDialog open={confirmStop} count={counts.pending} onKeep={() => setConfirmStop(false)} onStop={stopUploads} />
      </DialogContent>
    </Dialog>
  );
}
