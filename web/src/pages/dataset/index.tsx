import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";
import { ErrorState } from "@/components/error-state";
import { DATASETS_PATH } from "@/constants/app-paths";
import { useDatasetBinding } from "@/hooks/use-dataset-binding";
import type { DatasetDetailView } from "@/services/dataset-service";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { DatasetWorkspace } from "./dataset-workspace";
import { DatasetNotFound, DatasetPageSkeleton } from "./page-states";

/**
 * The dataset workspace (UI-11) at `/dataset/files?id=`: loads the dataset, decides between the workspace, "Dataset not
 * found" and a retryable error, and keeps the active workspace in step with the dataset's (D-26).
 *
 * The workspace binding lives in `useDatasetBinding`, shared with the other dataset pages.
 */
export default function DatasetPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const raw = params.get("id") ?? "";
  const id = /^[0-9a-f]{32}$/.test(raw) ? raw : "";

  const [leaving, setLeaving] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const lastShown = useRef<DatasetDetailView | null>(null);

  // The detail is not watched while the delete dialog is open (it loads its own copy) or once the dataset is gone: the
  // delete removes it from the cache and a watcher would ask for it again and meet a 404.
  const binding = useDatasetBinding({ datasetId: raw, watch: !leaving && !deleteDialogOpen });
  const { dataset, unbindable } = binding;
  if (dataset !== undefined) lastShown.current = dataset;
  // While a delete is in flight the cache entry disappears under the dialog: keep drawing the last copy until the page leaves.
  const shown = dataset ?? (leaving || deleteDialogOpen ? lastShown.current : null);

  const activeTenantId = useWorkspaceStore((state) => state.activeTenantId);
  const initialised = useWorkspaceStore((state) => state.initialisedFor !== null);

  useEffect(() => {
    document.title = shown === null || unbindable ? t("dataset.documentTitleFallback") : t("dataset.documentTitle", { name: shown.name });
  }, [shown, unbindable, t, i18n.language]);

  if (id === "" || unbindable) return <DatasetNotFound />;
  if (shown === null) {
    if (binding.state === "not-found") return <DatasetNotFound />;
    if (binding.state === "error") return <ErrorState level="h1" heading={t("dataset.error.heading")} onAction={binding.refetch} />;
    return <DatasetPageSkeleton />;
  }

  return (
    <DatasetWorkspace
      dataset={shown}
      ready={!initialised || activeTenantId === shown.tenantId}
      onDeleted={() => {
        setLeaving(true);
        navigate(DATASETS_PATH, { replace: true });
      }}
      onDeleteDialogChange={setDeleteDialogOpen}
    />
  );
}
