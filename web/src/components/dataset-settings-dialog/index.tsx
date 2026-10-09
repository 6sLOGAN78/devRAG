import { useRef, type MutableRefObject } from "react";
import { useTranslation } from "react-i18next";
import { ErrorState } from "@/components/error-state";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useModelsRequest } from "@/hooks/use-llm-request";
import type { DatasetDetailView, DatasetView } from "@/services/dataset-service";
import { SettingsForm } from "./settings-form";

export interface DatasetSettingsDialogProps {
  /** The dataset as listed. A detail view (with `chunkNum`) is also accepted and then also locks the embedding model on chunks. */
  dataset: DatasetView | DatasetDetailView;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Where focus goes when the dialog has closed. There is no trigger, so the owner decides. */
  onCloseAutoFocus?: (event: Event) => void;
}

function Header() {
  const { t } = useTranslation();
  return (
    <DialogHeader>
      <DialogTitle>{t("datasets.form.settingsTitle")}</DialogTitle>
      <DialogDescription>{t("datasets.form.settingsBody")}</DialogDescription>
    </DialogHeader>
  );
}

/** True once the dataset holds documents or chunks: the embedding model can no longer change (KB-06, plan 03-18). */
function isEmbeddingLocked(dataset: DatasetView | DatasetDetailView): boolean {
  return dataset.docNum > 0 || ("chunkNum" in dataset && dataset.chunkNum > 0);
}

function Body({ dataset, onClose, pendingRef }: { dataset: DatasetView | DatasetDetailView; onClose: () => void; pendingRef: MutableRefObject<boolean> }) {
  const { t } = useTranslation();
  const locked = isEmbeddingLocked(dataset);
  const models = useModelsRequest("embedding", !locked);
  if (locked) return <SettingsForm dataset={dataset} locked models={[]} pendingRef={pendingRef} onClose={onClose} />;
  if (models.data !== undefined) return <SettingsForm dataset={dataset} locked={false} models={models.data} pendingRef={pendingRef} onClose={onClose} />;
  if (models.isError) {
    return (
      <div className="flex flex-col gap-4">
        <Header />
        <ErrorState noun={t("models.errorNoun.settings")} onAction={() => void models.refetch()} />
      </div>
    );
  }
  return (
    <div data-testid="dataset-settings-skeleton" className="flex flex-col gap-4">
      <Header />
      <p role="status" className="sr-only">
        {t("datasets.form.loading")}
      </p>
      {[0, 1, 2].map((index) => (
        <Skeleton key={index} className="h-10 w-full" aria-hidden="true" />
      ))}
    </div>
  );
}

/**
 * Dataset settings (KB-06, UI-SPEC): name, description, visibility and, while the dataset has no documents, the
 * embedding model. Reuses the create dialog's schema, `ServerFieldError` and error placement. The caller draws the
 * control that opens it only for the dataset's creator, the workspace owner and admins; the server stays authoritative.
 * Mounted content lives only while open, so every opening starts from the dataset as listed.
 */
export function DatasetSettingsDialog({ dataset, open, onOpenChange, onCloseAutoFocus }: DatasetSettingsDialogProps) {
  const pendingRef = useRef(false);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="dataset-settings-dialog"
        onCloseAutoFocus={onCloseAutoFocus}
        onEscapeKeyDown={(event) => {
          if (pendingRef.current) event.preventDefault();
        }}
        onInteractOutside={(event) => {
          if (pendingRef.current) event.preventDefault();
        }}
      >
        <Body dataset={dataset} onClose={() => onOpenChange(false)} pendingRef={pendingRef} />
      </DialogContent>
    </Dialog>
  );
}
