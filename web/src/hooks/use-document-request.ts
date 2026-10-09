import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { deleteDocuments, listDocuments } from "@/services/document-service";
import { datasetQueryKey, datasetsKeyRoot } from "./use-knowledge-request";
import { useActiveWorkspace } from "./use-workspaces";

/** Documents per page of the dataset table (UI-SPEC). */
export const DOCUMENTS_PAGE_SIZE = 20;

/**
 * Query keys of the document data. Every key starts with `["ws", tenantId]` (TEN-13) and continues with the dataset,
 * so one prefix reaches every page and search of one dataset's documents.
 */
export const documentsKeyRoot = (tenantId: string | null, datasetId: string) => ["ws", tenantId, "documents", datasetId] as const;
export const documentsQueryKey = (tenantId: string | null, datasetId: string, page: number, keywords: string) =>
  ["ws", tenantId, "documents", datasetId, page, keywords] as const;

/**
 * Refreshes everything an upload or delete can change: the dataset's document pages, and BOTH dataset keys, because the
 * detail key (`["ws", t, "dataset", id]`) is not under the list root and both carry `doc_num`.
 */
export function invalidateDocumentData(queryClient: QueryClient, tenantId: string | null, datasetId: string): Promise<void> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: documentsKeyRoot(tenantId, datasetId) }),
    queryClient.invalidateQueries({ queryKey: datasetsKeyRoot(tenantId) }),
    queryClient.invalidateQueries({ queryKey: datasetQueryKey(tenantId, datasetId) }),
  ]).then(() => undefined);
}

/** A function that refreshes the active workspace's document and dataset data for one dataset. */
export function useInvalidateDocuments(): (datasetId: string) => void {
  const queryClient = useQueryClient();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return (datasetId) => void invalidateDocumentData(queryClient, tenantId, datasetId);
}

export interface DocumentsRequestInput {
  datasetId: string | undefined;
  page: number;
  keywords: string;
}

/** One page of a dataset's documents. Idle until a dataset id is given. No retry: a 404 or 403 is an answer, not a glitch. */
export function useDocumentsRequest({ datasetId, page, keywords }: DocumentsRequestInput) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const id = datasetId ?? "";
  return useQuery({
    queryKey: documentsQueryKey(tenantId, id, page, keywords),
    queryFn: () => listDocuments({ datasetId: id, page, pageSize: DOCUMENTS_PAGE_SIZE, keywords }),
    retry: false,
    enabled: tenantId !== null && id !== "",
  });
}

export interface DeleteDocumentsInput {
  datasetId: string;
  ids: string[];
}

/** Deletes documents (all or nothing). Not retried; a success refreshes the dataset's pages and both dataset keys. */
export function useDeleteDocumentsRequest() {
  const queryClient = useQueryClient();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useMutation({
    mutationFn: ({ datasetId, ids }: DeleteDocumentsInput) => deleteDocuments(datasetId, ids),
    retry: false,
    gcTime: 0,
    onSuccess: (_deleted, { datasetId }) => invalidateDocumentData(queryClient, tenantId, datasetId),
  });
}
