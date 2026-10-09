import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";
import { ErrorState } from "@/components/error-state";
import { DATASETS_PATH } from "@/constants/app-paths";
import { datasetQueryKey, useDatasetRequest } from "@/hooks/use-knowledge-request";
import type { DatasetDetailView } from "@/services/dataset-service";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { DatasetWorkspace } from "./dataset-workspace";
import { datasetPageState } from "./errors";
import { DatasetNotFound, DatasetPageSkeleton } from "./page-states";

/** Dataset ids are 32 lowercase hex characters. Anything else is "not found" without a request (T-03-31-01). */
const DATASET_ID = /^[0-9a-f]{32}$/;

/**
 * The dataset workspace (UI-11) at `/dataset/files?id=`: loads the dataset, decides between the workspace, "Dataset not
 * found" and a retryable error, and keeps the active workspace in step with the dataset's (D-26).
 *
 * Binding without a loop. `boundTenantRef` holds the workspace of the dataset on show. When the first load reports a
 * workspace other than the active one (a deep link into a joined workspace) the detail is seeded under the new
 * workspace's key, the ref is written BEFORE the store changes, and only then is the workspace switched. The effect that
 * leaves for /datasets fires when the active workspace differs from the ref, i.e. only for a switch the user made.
 */
export default function DatasetPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const raw = params.get("id") ?? "";
  const id = DATASET_ID.test(raw) ? raw : "";

  const [leaving, setLeaving] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [unbindable, setUnbindable] = useState(false);
  const boundTenantRef = useRef<string | null>(null);
  const lastShown = useRef<DatasetDetailView | null>(null);

  // The detail is not watched while the delete dialog is open (it loads its own copy) or once the dataset is gone: the
  // delete removes it from the cache and a watcher would ask for it again and meet a 404.
  const detail = useDatasetRequest(id === "" ? undefined : id, !leaving && !deleteDialogOpen);
  const dataset = detail.data;
  if (dataset !== undefined) lastShown.current = dataset;
  // While a delete is in flight the cache entry disappears under the dialog: keep drawing the last copy until the page leaves.
  const shown = dataset ?? (leaving || deleteDialogOpen ? lastShown.current : null);

  const activeTenantId = useWorkspaceStore((state) => state.activeTenantId);
  const initialised = useWorkspaceStore((state) => state.initialisedFor !== null);

  // A different dataset is a different binding.
  useEffect(() => {
    boundTenantRef.current = null;
    setUnbindable(false);
  }, [id]);

  // Bind once per dataset, once the workspace list is known (a store that is not initialised refuses every switch).
  useEffect(() => {
    if (dataset === undefined || !initialised || boundTenantRef.current !== null) return;
    const tenant = dataset.tenantId;
    boundTenantRef.current = tenant;
    if (useWorkspaceStore.getState().activeTenantId === tenant) return;
    queryClient.setQueryData(datasetQueryKey(tenant, id), dataset);
    if (!useWorkspaceStore.getState().bindActive(tenant)) {
      // The caller is not a member of that workspace as far as the list knows: show nothing of it.
      boundTenantRef.current = null;
      queryClient.removeQueries({ queryKey: datasetQueryKey(tenant, id) });
      setUnbindable(true);
    }
  }, [dataset, initialised, id, queryClient]);

  // The user switched workspace: the dataset belongs to the previous one. Reads the store, not the render's value, so the
  // switch made by the effect above (ref already written) is never mistaken for a user switch.
  useEffect(() => {
    const bound = boundTenantRef.current;
    const active = useWorkspaceStore.getState().activeTenantId;
    if (bound !== null && active !== null && active !== bound) navigate(DATASETS_PATH, { replace: true });
  }, [activeTenantId, navigate]);

  useEffect(() => {
    document.title = shown === null || unbindable ? t("dataset.documentTitleFallback") : t("dataset.documentTitle", { name: shown.name });
  }, [shown, unbindable, t, i18n.language]);

  if (id === "" || unbindable) return <DatasetNotFound />;
  if (shown === null) {
    if (detail.isError) {
      if (datasetPageState(detail.error) === "notFound") return <DatasetNotFound />;
      return <ErrorState level="h1" heading={t("dataset.error.heading")} onAction={() => void detail.refetch()} />;
    }
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
