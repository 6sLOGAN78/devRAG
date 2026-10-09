import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useRef, useState } from "react";
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
import { invalidateDocumentData, useDeleteDocumentsRequest } from "@/hooks/use-document-request";
import { useActiveWorkspace } from "@/hooks/use-workspaces";
import { deleteFailureOf, isCancelled } from "@/pages/datasets/errors";
import { notifySuccess } from "@/services/notify";

export interface DeleteDocumentDialogProps {
  datasetId: string;
  /** The dataset's name, for the body. User text. */
  datasetName: string;
  /** The document to delete; the name is user text. */
  document: { id: string; name: string };
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called once the document is gone (deleted now, or already gone). The table moves focus and steps back a page. */
  onSuccess?: () => void;
  /** Where focus goes when the dialog has closed. The row is usually gone, so the owner decides. */
  onCloseAutoFocus?: (event: Event) => void;
}

/**
 * Delete document (DOC-14): an `AlertDialog` naming the document and its dataset, "Keep document" focused first. The
 * API removes a batch all or nothing, so exactly one document is deleted per request. A failure keeps the dialog open
 * with fixed copy (checker flag 4); a 403 shows the lost-permission alert and refetches (D-09). Standalone: do not open
 * it over another dialog.
 */
export function DeleteDocumentDialog({ datasetId, datasetName, document, open, onOpenChange, onSuccess, onCloseAutoFocus }: DeleteDocumentDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const workspaceName = useWorkspaceName(tenantId ?? "");
  const remove = useDeleteDocumentsRequest();
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState<string | null>(null);

  async function confirm(): Promise<void> {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setAlert(null);
    let finished = false;
    try {
      await remove.mutateAsync({ datasetId, ids: [document.id] });
      notifySuccess(t("datasets.documentDeleted"));
      finished = true;
    } catch (error) {
      if (!isCancelled(error)) {
        const failure = deleteFailureOf(error, "doc");
        if (failure.kind === "gone") {
          void invalidateDocumentData(queryClient, tenantId, datasetId);
          finished = true;
        } else if (failure.kind === "forbidden") {
          void invalidateDocumentData(queryClient, tenantId, datasetId);
          setAlert(t(failure.key, { workspace: workspaceName }));
        } else {
          setAlert(t(failure.key));
        }
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
    if (finished) {
      onOpenChange(false);
      onSuccess?.();
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent
        data-testid="document-delete-dialog"
        onCloseAutoFocus={onCloseAutoFocus}
        onEscapeKeyDown={(event) => {
          if (inFlight.current) event.preventDefault();
        }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle>{t("datasets.documentDelete.title")}</AlertDialogTitle>
          <AlertDialogDescription className="break-words">{t("datasets.documentDelete.body", { name: document.name, dataset: datasetName })}</AlertDialogDescription>
        </AlertDialogHeader>
        {alert === null ? null : <Alert data-testid="document-delete-error">{alert}</Alert>}
        <AlertDialogFooter>
          <AlertDialogCancel
            data-testid="document-delete-keep"
            onClick={(event) => {
              if (inFlight.current) event.preventDefault();
            }}
          >
            {t("datasets.documentDelete.keep")}
          </AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            data-testid="document-delete-confirm"
            aria-disabled={busy ? true : undefined}
            aria-busy={busy || undefined}
            className="aria-disabled:pointer-events-none aria-disabled:opacity-50"
            onClick={(event) => {
              event.preventDefault();
              void confirm();
            }}
          >
            {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
            {t("datasets.documentDelete.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
