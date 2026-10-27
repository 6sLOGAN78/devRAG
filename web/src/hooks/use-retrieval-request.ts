import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { ApiError } from "@/services/http";
import { searchDataset, type RetrievalInput } from "@/services/retrieval-service";
import { useActiveWorkspace } from "./use-workspaces";

/** A user-triggered read, never retried: every attempt spends an embedding request. */
export function useRetrievalSearch() {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useMutation({
    mutationFn: (input: RetrievalInput) => {
      if (!tenantId) throw new ApiError({ code: 400, status: 400, message: "Choose a workspace before searching.", data: { reason: "workspace_unknown" } });
      return searchDataset({ ...input, tenantId });
    },
    retry: false, gcTime: 0,
  });
}
/** Snapshot/run id change only on Run; paging is an explicit new provider call. */
export function useRetrievalResults(datasetId: string, snapshot: Omit<RetrievalInput, "datasetId" | "page"> | null, page: number, runId: number, enabled: boolean) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useQuery({
    queryKey: ["ws", tenantId, "retrieval", datasetId, snapshot, page, runId],
    queryFn: () => searchDataset({ ...snapshot!, datasetId, page, tenantId: tenantId! }), enabled: enabled && tenantId !== null && snapshot !== null,
    retry: false, staleTime: Infinity, gcTime: 0,
    placeholderData: (previous, query) => query?.queryKey[1] === tenantId && query.queryKey[3] === datasetId ? keepPreviousData(previous) : undefined,
  });
}
