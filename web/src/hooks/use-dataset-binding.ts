import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { DATASETS_PATH } from "@/constants/app-paths";
import { datasetPageState } from "@/pages/dataset/errors";
import type { DatasetDetailView } from "@/services/dataset-service";
import { useWorkspaceStore } from "@/stores/workspace-store";
import { datasetQueryKey, useDatasetRequest } from "./use-knowledge-request";

/** Dataset ids are 32 lowercase hex characters. Anything else is "not found" without a request (T-03-31-01). */
const DATASET_ID = /^[0-9a-f]{32}$/;

/** `loading`: nothing known yet. `ready`: the dataset is on show. `not-found`: missing, malformed id or unbindable. `error`: retryable. `leaving`: the user switched workspace and the page is navigating away. */
export type DatasetBindingState = "loading" | "ready" | "not-found" | "error" | "leaving";

export interface DatasetBindingOptions {
  /** The raw `id` from the address bar; anything that is not a dataset id counts as not found without a request. */
  datasetId: string | null | undefined;
  /** False stops the detail query without changing its key (a delete in flight must not refetch what it removes). Default true. */
  watch?: boolean;
}

export interface DatasetBinding {
  dataset: DatasetDetailView | undefined;
  state: DatasetBindingState;
  /** True once the store is initialised and the active workspace is the dataset's: dataset-scoped requests may be sent. */
  bound: boolean;
  /** The workspace list never allowed the dataset's workspace; show nothing of it. */
  unbindable: boolean;
  error: unknown;
  refetch: () => void;
}

/**
 * Binds the active workspace to the dataset on show (D-26), for every page that opens a dataset by `?id=`.
 *
 * Binding without a loop. `boundTenantRef` holds the workspace of the dataset on show. When the first load reports a
 * workspace other than the active one (a deep link into a joined workspace) the detail is seeded under the new
 * workspace's key, the ref is written BEFORE the store changes, and only then is the workspace switched. The effect that
 * leaves for /datasets fires when the active workspace differs from the ref, i.e. only for a switch the user made.
 *
 * Pages must send no dataset-scoped request until `bound` is true (FE-02, T-04-25-01).
 */
export function useDatasetBinding({ datasetId, watch = true }: DatasetBindingOptions): DatasetBinding {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const id = datasetId !== null && datasetId !== undefined && DATASET_ID.test(datasetId) ? datasetId : "";

  const [leaving, setLeaving] = useState(false);
  const [unbindable, setUnbindable] = useState(false);
  const boundTenantRef = useRef<string | null>(null);

  const detail = useDatasetRequest(id === "" ? undefined : id, watch);
  const dataset = detail.data;

  const activeTenantId = useWorkspaceStore((state) => state.activeTenantId);
  const initialised = useWorkspaceStore((state) => state.initialisedFor !== null);

  // A different dataset is a different binding.
  useEffect(() => {
    boundTenantRef.current = null;
    setUnbindable(false);
    setLeaving(false);
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
    if (bound !== null && active !== null && active !== bound) {
      setLeaving(true);
      navigate(DATASETS_PATH, { replace: true });
    }
  }, [activeTenantId, navigate]);

  const bound = dataset !== undefined && initialised && !unbindable && activeTenantId === dataset.tenantId;

  let state: DatasetBindingState;
  if (id === "" || unbindable) state = "not-found";
  else if (leaving) state = "leaving";
  else if (dataset !== undefined) state = "ready";
  else if (detail.isError) state = datasetPageState(detail.error) === "notFound" ? "not-found" : "error";
  else state = "loading";

  return { dataset, state, bound, unbindable, error: detail.error, refetch: () => void detail.refetch() };
}
