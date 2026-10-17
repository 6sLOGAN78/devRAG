import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { createChunk, listChunks, updateChunk, type ChunkChanges } from "@/services/chunk-service";
import type { DocumentDetailView } from "@/services/document-service";
import { documentDetailKey, invalidateDocumentData } from "./use-document-request";
import { useActiveWorkspace } from "./use-workspaces";

/** Chunks per page of the inspector list (UI-SPEC). */
export const CHUNKS_PAGE_SIZE = 20;

export type ChunkShow = "all" | "on" | "off";

export const chunksKeyRoot = (tenantId: string | null, datasetId: string, docId: string) => ["ws", tenantId, "chunks", datasetId, docId] as const;
export const chunksKey = (tenantId: string | null, datasetId: string, docId: string, page: number, keywords: string, show: ChunkShow) =>
  ["ws", tenantId, "chunks", datasetId, docId, page, keywords, show] as const;

export interface ChunksRequestInput {
  datasetId: string | undefined;
  docId: string | undefined;
  page: number;
  keywords: string;
  show: ChunkShow;
  enabled?: boolean;
}

/** One page of a document's chunks. Keeps the previous page while loading; never polls (see `useChunkRefresh`). */
export function useChunksRequest({ datasetId, docId, page, keywords, show, enabled = true }: ChunksRequestInput) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const dataset = datasetId ?? "";
  const doc = docId ?? "";
  return useQuery({
    queryKey: chunksKey(tenantId, dataset, doc, page, keywords, show),
    queryFn: () => listChunks({ datasetId: dataset, docId: doc, page, size: CHUNKS_PAGE_SIZE, keywords, available: show === "all" ? undefined : show === "on" }),
    retry: false,
    placeholderData: keepPreviousData,
    enabled: enabled && tenantId !== null && dataset !== "" && doc !== "",
  });
}

/**
 * Refetches the chunk list when the polled document detail reports a different chunk count, and once when its parse
 * stops running. Chunks appear as they are indexed without the list itself polling.
 */
export function useChunkRefresh(detail: Pick<DocumentDetailView, "id" | "datasetId" | "chunkCount" | "run"> | undefined): void {
  const queryClient = useQueryClient();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const previous = useRef<{ id: string; chunkCount: number; run: string } | null>(null);
  useEffect(() => {
    if (detail === undefined) return;
    const before = previous.current;
    previous.current = { id: detail.id, chunkCount: detail.chunkCount, run: detail.run };
    if (before === null || before.id !== detail.id) return;
    if (before.chunkCount !== detail.chunkCount || (before.run === "1" && detail.run !== "1")) {
      void queryClient.invalidateQueries({ queryKey: chunksKeyRoot(tenantId, detail.datasetId, detail.id) });
    }
  }, [detail, queryClient, tenantId]);
}

/** Everything a chunk write can change: the chunk pages, the document, the document pages and both dataset keys. */
function refreshAfterChunkWrite(queryClient: QueryClient, tenantId: string | null, datasetId: string, docId: string): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: chunksKeyRoot(tenantId, datasetId, docId) }),
    queryClient.invalidateQueries({ queryKey: documentDetailKey(tenantId, datasetId, docId) }),
    invalidateDocumentData(queryClient, tenantId, datasetId),
  ]);
}

export interface CreateChunkInput {
  datasetId: string;
  docId: string;
  content: string;
}

/** Adds a chunk by hand. Not retried; refreshes in `onSettled` so a timed-out write still shows the truth. */
export function useCreateChunkRequest() {
  const queryClient = useQueryClient();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useMutation({
    mutationFn: ({ datasetId, docId, content }: CreateChunkInput) => createChunk(datasetId, docId, content),
    retry: false,
    gcTime: 0,
    onSettled: (_data, _error, { datasetId, docId }) => refreshAfterChunkWrite(queryClient, tenantId, datasetId, docId),
  });
}

export interface UpdateChunkInput {
  datasetId: string;
  docId: string;
  chunkId: string;
  changes: ChunkChanges;
}

/** Edits a chunk's text (45 s timeout, set by the service) or switch. Not retried; refreshes in `onSettled`. */
export function useUpdateChunkRequest() {
  const queryClient = useQueryClient();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useMutation({
    mutationFn: ({ datasetId, docId, chunkId, changes }: UpdateChunkInput) => updateChunk(datasetId, docId, chunkId, changes),
    retry: false,
    gcTime: 0,
    onSettled: (_data, _error, { datasetId, docId }) => refreshAfterChunkWrite(queryClient, tenantId, datasetId, docId),
  });
}
