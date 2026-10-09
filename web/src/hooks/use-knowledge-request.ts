import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createDataset, getDataset, listDatasets, type CreateDatasetInput } from "@/services/dataset-service";
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

/** One dataset with its upload limits, under the active workspace's key. Idle until an id is given. */
export function useDatasetRequest(id: string | undefined) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useQuery({
    queryKey: datasetQueryKey(tenantId, id ?? ""),
    queryFn: () => getDataset(id ?? ""),
    retry: false,
    enabled: tenantId !== null && id !== undefined && id !== "",
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
