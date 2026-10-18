import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import {
  createDataset,
  deleteDatasets,
  getDataset,
  listDatasets,
  updateDataset,
  updateDatasetChunking,
  type CreateDatasetInput,
  type DatasetChanges,
  type DatasetChunkingInput,
} from "@/services/dataset-service";
import { useActiveWorkspace } from "./use-workspaces";

/** Datasets per gallery page (UI-SPEC). */
export const DATASETS_PAGE_SIZE = 12;

/**
 * Query keys of the dataset data. Every key starts with `["ws", tenantId]`, so switching workspace never shows another
 * workspace's cache (TEN-13, D-26). `dropSessionState` clears the whole cache on sign out.
 */
export const datasetsKeyRoot = (tenantId: string | null) => ["ws", tenantId, "datasets"] as const;
export const datasetsQueryKey = (tenantId: string | null, page: number, keywords: string) => ["ws", tenantId, "datasets", page, keywords] as const;
export const datasetQueryKey = (tenantId: string | null, id: string) => ["ws", tenantId, "dataset", id] as const;

export interface DatasetsRequestInput {
  page: number;
  keywords: string;
}

/** One page of the active workspace's datasets. No retry: a 503 or 403 is an answer, not a glitch. */
export function useDatasetsRequest({ page, keywords }: DatasetsRequestInput) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useQuery({
    queryKey: datasetsQueryKey(tenantId, page, keywords),
    queryFn: () => listDatasets({ tenantId: tenantId ?? "", page, pageSize: DATASETS_PAGE_SIZE, keywords }),
    retry: false,
    enabled: tenantId !== null,
  });
}

/**
 * One dataset with its upload limits, under the active workspace's key. Idle until an id is given. `enabled` lets a
 * caller stop the query without changing its key (a delete in flight must not refetch the dataset it is removing).
 */
export function useDatasetRequest(id: string | undefined, enabled = true) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useQuery({
    queryKey: datasetQueryKey(tenantId, id ?? ""),
    queryFn: () => getDataset(id ?? ""),
    retry: false,
    enabled: enabled && tenantId !== null && id !== undefined && id !== "",
  });
}

/** Creates a dataset. Not retried (a retry could create a second one); a success refetches only the workspace's lists. */
export function useCreateDatasetRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateDatasetInput) => createDataset(input),
    retry: false,
    gcTime: 0,
    onSuccess: (_data, variables) => queryClient.invalidateQueries({ queryKey: datasetsKeyRoot(variables.tenantId) }),
  });
}

export interface UpdateDatasetInput {
  id: string;
  /** The dataset's workspace, so the right lists are refreshed even if the active workspace changes meanwhile. */
  tenantId: string;
  changes: DatasetChanges;
}

/**
 * Saves dataset settings. Not retried. A success refreshes the workspace's lists and the dataset's detail (the detail
 * carries upload limits the PUT answer does not, so it is refetched rather than overwritten).
 */
export function useUpdateDatasetRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, changes }: UpdateDatasetInput) => updateDataset(id, changes),
    retry: false,
    gcTime: 0,
    onSuccess: (_data, { id, tenantId }) => refreshDataset(queryClient, tenantId, id),
  });
}

export interface UpdateDatasetChunkingInput {
  id: string;
  tenantId: string;
  changes: DatasetChunkingInput;
}

/** Saves the dataset's default chunking method and values. Not retried; refreshes the detail and the lists in `onSettled`. */
export function useUpdateDatasetChunkingRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, changes }: UpdateDatasetChunkingInput) => updateDatasetChunking(id, changes),
    retry: false,
    gcTime: 0,
    onSettled: (_data, _error, { id, tenantId }) => refreshDataset(queryClient, tenantId, id),
  });
}

/** Refetches the lists of one workspace and the detail of one dataset (after a save, or a refusal that shows the cache is stale). */
export function refreshDataset(queryClient: QueryClient, tenantId: string | null, id: string): Promise<void> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: datasetsKeyRoot(tenantId) }),
    queryClient.invalidateQueries({ queryKey: datasetQueryKey(tenantId, id) }),
  ]).then(() => undefined);
}

export interface DeleteDatasetInput {
  id: string;
  tenantId: string;
}

/**
 * Deletes ONE dataset (the API authorises a batch all or nothing). Not retried. A success drops the deleted dataset's
 * detail from the cache, so nothing asks for it again and meets a 404, then refreshes the workspace's lists.
 */
export function useDeleteDatasetsRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, tenantId }: DeleteDatasetInput) => deleteDatasets([id], tenantId),
    retry: false,
    gcTime: 0,
    onSuccess: (_deleted, { id, tenantId }) => {
      queryClient.removeQueries({ queryKey: datasetQueryKey(tenantId, id) });
      return queryClient.invalidateQueries({ queryKey: datasetsKeyRoot(tenantId) });
    },
  });
}
