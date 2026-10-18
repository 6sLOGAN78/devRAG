import { Loader2, TriangleAlert } from "lucide-react";
import { useRef, useState, type MutableRefObject } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert } from "@/components/ui/alert";
import { useWorkspaceName } from "@/hooks/use-dataset-permissions";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import type { ConfirmCount } from "@/services/document-service";
import type { PendingConfirm, ReplaceOutcome } from "./parse-actions";

export interface ReparseDialogProps {
  /** The server's refusal with its counts; null while the dialog is closed. */
  confirm: PendingConfirm | null;
  /** Resends the request with `confirm_replace`. */
  onReplace(): Promise<ReplaceOutcome>;
  onDismiss(): void;
  /** The dialog has no trigger, so its owner says where focus goes when it has closed. */
  onCloseAutoFocus(event: Event): void;
}

interface BodyProps {
  confirm: PendingConfirm;
  flight: MutableRefObject<boolean>;
  onReplace(): Promise<ReplaceOutcome>;
}

/**
 * Everything inside the dialog that can change between openings. It lives inside the dialog's content, which exists
 * only while the dialog is open, and is keyed by the opening, so an error from document A is never shown for B (FE-04).
 */
function ReparseBody({ confirm, flight, onReplace }: BodyProps) {
  const { t } = useTranslation();
  const workspaceName = useWorkspaceName(useActiveWorkspace()?.tenantId ?? "");
  const [busy, setBusy] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [changed, setChanged] = useState(false);
  const many = confirm.ids.length > 1;
  const documents = confirm.documents;
  const sum = (pick: (d: ConfirmCount) => number) => documents.reduce((total, d) => total + pick(d), 0);
  const chunks = sum((d) => d.chunkCount);
  const edited = sum((d) => d.editedCount);
  const manual = sum((d) => d.manualCount);
  const loss = edited + manual > 0;
  const number = new Intl.NumberFormat();

  async function replace(): Promise<void> {
    if (flight.current) return;
    flight.current = true;
    setBusy(true);
    setErrorKey(null);
    setChanged(false);
    try {
      const outcome = await onReplace();
      if (outcome.kind === "counts") setChanged(true);
      else if (outcome.kind === "failed") setErrorKey(outcome.key);
    } finally {
      flight.current = false;
      setBusy(false);
    }
  }

  const rows: Array<{ id: string; label: string; value: number; warn: boolean }> = [
    { id: "reparse-chunks", label: t("datasets.reparse.count.chunks"), value: chunks, warn: false },
    { id: "reparse-edited", label: t("datasets.reparse.count.edited"), value: edited, warn: loss },
    { id: "reparse-manual", label: t("datasets.reparse.count.manual"), value: manual, warn: loss },
  ];

  return (
    <>
      <AlertDialogHeader>
        <AlertDialogTitle>{many ? t("datasets.reparse.titleMany", { count: confirm.ids.length }) : t("datasets.reparse.title")}</AlertDialogTitle>
        <AlertDialogDescription className="break-words">
          {many ? t("datasets.reparse.bodyMany", { affected: documents.length }) : t("datasets.reparse.body", { name: documents[0]?.name ?? "" })}
        </AlertDialogDescription>
      </AlertDialogHeader>
      <dl className="flex flex-col gap-2 text-sm">
        {rows.map((row) => (
          <div key={row.id} className="flex items-start justify-between gap-4">
            <dt className="flex items-start gap-1 font-normal text-muted-foreground">
              {row.warn ? <TriangleAlert className="mt-0.5 size-4 shrink-0 text-foreground" aria-hidden="true" /> : null}
              {row.label}
            </dt>
            <dd data-testid={row.id} className="font-semibold tabular-nums">
              {number.format(row.value)}
            </dd>
          </div>
        ))}
      </dl>
      <p data-testid="reparse-loss-note" className="text-sm font-normal">
        {loss ? t("datasets.reparse.lossNote") : many ? t("datasets.reparse.noLossMany") : t("datasets.reparse.noLoss")}
      </p>
      {many ? (
        <ul data-testid="reparse-list" className="max-h-40 overflow-y-auto rounded-md border">
          {documents.map((d) => (
            <li key={d.id} className="flex flex-col border-b px-3 py-2 last:border-b-0">
              <span className="break-all text-sm font-semibold">{d.name}</span>
              <span className="text-xs font-normal text-muted-foreground">{t("datasets.files.detail.chunks", { count: d.chunkCount })}</span>
              {d.editedCount + d.manualCount > 0 ? (
                <span className="text-xs font-normal text-muted-foreground">{t("datasets.reparse.rowHand", { edited: d.editedCount, manual: d.manualCount })}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="text-xs font-normal text-muted-foreground">{many ? t("datasets.reparse.searchNoteMany") : t("datasets.reparse.searchNote")}</p>
      {changed ? (
        <Alert variant="info" data-testid="reparse-changed">
          {t("datasets.reparse.changed")}
        </Alert>
      ) : null}
      {errorKey === null ? null : <Alert data-testid="reparse-error">{t(errorKey, { workspace: workspaceName })}</Alert>}
      <AlertDialogFooter>
        <AlertDialogCancel
          data-testid="reparse-keep"
          onClick={(event) => {
            if (flight.current) event.preventDefault();
          }}
        >
          {t("datasets.reparse.keep")}
        </AlertDialogCancel>
        <AlertDialogAction
          variant="destructive"
          data-testid="reparse-confirm"
          aria-disabled={busy ? true : undefined}
          aria-busy={busy || undefined}
          className="aria-disabled:pointer-events-none aria-disabled:opacity-50"
          onClick={(event) => {
            event.preventDefault();
            void replace();
          }}
        >
          {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
          {t("datasets.reparse.confirm")}
        </AlertDialogAction>
      </AlertDialogFooter>
    </>
  );
}

/**
 * Parse again for one document or several (D-03, D-04, D-09): a standalone `AlertDialog` with no trigger, opened only
 * when the server answered 409 `confirm_required`. "Keep chunks" has the first focus; "Replace chunks" resends with
 * `confirm_replace`. While that request is in flight the dialog cannot be dismissed. Never open it over another dialog
 * or a sheet.
 */
export function ReparseDialog({ confirm, onReplace, onDismiss, onCloseAutoFocus }: ReparseDialogProps) {
  const flight = useRef(false);
  // Kept while the dialog animates out, so it does not collapse to an empty box; the content unmounts right after.
  const shown = useRef<PendingConfirm | null>(null);
  if (confirm !== null) shown.current = confirm;
  const current = confirm ?? shown.current;
  return (
    <AlertDialog
      open={confirm !== null}
      onOpenChange={(open) => {
        if (!open && !flight.current) onDismiss();
      }}
    >
      <AlertDialogContent
        data-testid="reparse-dialog"
        className="max-w-md"
        onCloseAutoFocus={onCloseAutoFocus}
        onEscapeKeyDown={(event) => {
          if (flight.current) event.preventDefault();
        }}
      >
        {current === null ? null : <ReparseBody key={current.session} confirm={current} flight={flight} onReplace={onReplace} />}
      </AlertDialogContent>
    </AlertDialog>
  );
}
