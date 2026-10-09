import { useQueryClient } from "@tanstack/react-query";
import { CircleAlert, Loader2 } from "lucide-react";
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
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaceName } from "@/hooks/use-dataset-permissions";
import { datasetQueryKey, datasetsKeyRoot, refreshDataset, useDatasetRequest, useDeleteDatasetsRequest } from "@/hooks/use-knowledge-request";
import { deleteFailureOf, isCancelled } from "@/pages/datasets/errors";
import { notifySuccess } from "@/services/notify";

/** What the confirmation needs to know about the dataset it deletes. The name is user text. */
export interface DeleteDatasetTarget {
  id: string;
  name: string;
  /** The dataset's workspace, sent with the delete and used to refresh the right lists. */
  tenantId: string;
}

export interface DeleteDatasetDialogProps {
  dataset: DeleteDatasetTarget;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called once the dataset is gone (deleted now, or already gone). The owner moves focus or navigates. */
  onSuccess?: () => void;
  /** Where focus goes when the dialog has closed. There is no trigger, so the owner decides. */
  onCloseAutoFocus?: (event: Event) => void;
}

interface BodyProps {
  dataset: DeleteDatasetTarget;
  onClose: () => void;
  onSuccess?: () => void;
  pendingRef: MutableRefObject<boolean>;
}

/**
 * Mounted only while the dialog is open, so every opening loads the document count again. The count is the one thing
 * the confirmation states, so it is never guessed: Delete stays `aria-disabled` until a request that started after
 * the dialog opened has answered, and a failed request shows a retry and keeps Delete disabled (D-10, T-03-25-03).
 */
function Body({ dataset, onClose, onSuccess, pendingRef }: BodyProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const workspaceName = useWorkspaceName(dataset.tenantId);
  // Set when Delete is pressed: from then on the detail is not asked for again (the dataset is going away and the
  // request would meet a 404). The count that was fresh at that moment stays on screen while the dialog closes.
  const [settled, setSettled] = useState(false);
  const detail = useDatasetRequest(dataset.id, !settled);
  const remove = useDeleteDatasetsRequest();
  const lastCount = useRef<number | null>(null);
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [alert, setAlert] = useState<string | null>(null);

  if (detail.data !== undefined) lastCount.current = detail.data.docNum;
  const count = detail.data?.docNum ?? lastCount.current;
  const failed = detail.isError && !detail.isFetching && !settled;
  const loading = !settled && (detail.isFetching || count === null) && !failed;
  const ready = count !== null && !loading && !failed;

  async function confirm(): Promise<void> {
    if (inFlight.current || !ready) return;
    inFlight.current = true;
    pendingRef.current = true;
    setBusy(true);
    setAlert(null);
    setSettled(true);
    let finished = false;
    try {
      await remove.mutateAsync({ id: dataset.id, tenantId: dataset.tenantId });
      notifySuccess(t("datasets.deleted"));
      finished = true;
    } catch (error) {
      if (!isCancelled(error)) {
        const failure = deleteFailureOf(error, "dataset");
        if (failure.kind === "gone") {
          // Deleted elsewhere in the meantime: the dataset is gone either way, so refresh and close without a toast.
          queryClient.removeQueries({ queryKey: datasetQueryKey(dataset.tenantId, dataset.id) });
          void queryClient.invalidateQueries({ queryKey: datasetsKeyRoot(dataset.tenantId) });
          finished = true;
        } else if (failure.kind === "forbidden") {
          // The server is authoritative: the role changed. Say so, and fetch the dataset and the lists again.
          setSettled(false);
          void refreshDataset(queryClient, dataset.tenantId, dataset.id);
          setAlert(t(failure.key, { workspace: workspaceName }));
        } else {
          setAlert(t(failure.key));
        }
      }
    } finally {
      inFlight.current = false;
      pendingRef.current = false;
      setBusy(false);
    }
    if (finished) {
      onClose();
      onSuccess?.();
    }
  }

  let description;
  if (failed) {
    description = (
      <>
        <span className="flex items-start gap-1 text-destructive">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>{t("datasets.delete.countError")}</span>
        </span>
        <Button type="button" variant="ghost" size="sm" data-testid="dataset-delete-retry" className="mt-2 self-start" onClick={() => void detail.refetch()}>
          {t("errorState.action")}
        </Button>
      </>
    );
  } else if (!ready) {
    description = (
      <>
        <Skeleton data-testid="dataset-delete-count-skeleton" className="h-12 w-full" aria-hidden="true" />
        <span role="status" className="sr-only">
          {t("datasets.delete.loading")}
        </span>
      </>
    );
  } else if (count === 0) {
    description = t("datasets.delete.bodyEmpty", { name: dataset.name });
  } else {
    description = t("datasets.delete.body", { name: dataset.name, count });
  }

  return (
    <>
      <AlertDialogHeader>
        <AlertDialogTitle>{t("datasets.delete.title")}</AlertDialogTitle>
        <AlertDialogDescription asChild>
          <div data-testid="dataset-delete-count" className="flex flex-col break-words">
            {description}
          </div>
        </AlertDialogDescription>
      </AlertDialogHeader>
      {alert === null ? null : <Alert data-testid="dataset-delete-error">{alert}</Alert>}
      <AlertDialogFooter>
        <AlertDialogCancel
          data-testid="dataset-delete-keep"
          onClick={(event) => {
            if (inFlight.current) event.preventDefault();
          }}
        >
          {t("datasets.delete.keep")}
        </AlertDialogCancel>
        <AlertDialogAction
          variant="destructive"
          data-testid="dataset-delete-confirm"
          aria-disabled={ready && !busy ? undefined : true}
          aria-busy={busy || undefined}
          className="aria-disabled:pointer-events-none aria-disabled:opacity-50"
          onClick={(event) => {
            event.preventDefault();
            void confirm();
          }}
        >
          {busy ? <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
          {t("datasets.delete.confirm")}
        </AlertDialogAction>
      </AlertDialogFooter>
    </>
  );
}

/**
 * Delete dataset (KB-07, D-10): an `AlertDialog` that names the dataset, loads and states its current document count,
 * defaults focus to "Keep dataset" and stays open until the server answers. The API authorises a batch all or nothing,
 * so exactly one dataset is deleted per request. A standalone alert dialog: do not open it over another dialog.
 */
export function DeleteDatasetDialog({ dataset, open, onOpenChange, onSuccess, onCloseAutoFocus }: DeleteDatasetDialogProps) {
  const pendingRef = useRef(false);
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent
        data-testid="dataset-delete-dialog"
        onCloseAutoFocus={onCloseAutoFocus}
        onEscapeKeyDown={(event) => {
          if (pendingRef.current) event.preventDefault();
        }}
      >
        <Body dataset={dataset} onClose={() => onOpenChange(false)} onSuccess={onSuccess} pendingRef={pendingRef} />
      </AlertDialogContent>
    </AlertDialog>
  );
}
