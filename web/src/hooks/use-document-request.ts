import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  deleteDocuments,
  getDocument,
  listDocuments,
  parseDocuments,
  setDocumentsEnabled,
  updateDocumentSettings,
  type DocumentSettingsChanges,
  type DocumentView,
} from "@/services/document-service";
import { POLL_INTERVAL_MS, ingestionKeyRoot } from "./use-ingestion-request";
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
export const documentDetailKey = (tenantId: string | null, datasetId: string, docId: string) =>
  [...documentsKeyRoot(tenantId, datasetId), "detail", docId] as const;

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

/** Failed polls in a row after which the page says live updates are paused (UI-SPEC). */
export const POLL_FAILURE_LIMIT = 3;

/**
 * Counts failed refreshes of a polled query in a row: three set `pollPaused`, one success clears it. Reads the query's
 * own timestamps, so it needs nothing from the caller beyond the query result.
 */
export function usePollHealth(query: { errorUpdatedAt: number; dataUpdatedAt: number }): { pollPaused: boolean } {
  const [failures, setFailures] = useState(0);
  const seen = useRef({ error: query.errorUpdatedAt, data: query.dataUpdatedAt });
  useEffect(() => {
    const before = seen.current;
    seen.current = { error: query.errorUpdatedAt, data: query.dataUpdatedAt };
    if (query.dataUpdatedAt !== before.data) setFailures(0);
    else if (query.errorUpdatedAt !== before.error) setFailures((count) => count + 1);
  }, [query.errorUpdatedAt, query.dataUpdatedAt]);
  return { pollPaused: failures >= POLL_FAILURE_LIMIT };
}

/**
 * One page of a dataset's documents. Idle until a dataset id is given. No retry: a 404 or 403 is an answer, not a glitch.
 * Keeps the previous page while the next loads (FE-01) and polls every 2000 ms only while a row is parsing, never in a hidden tab.
 */
export function useDocumentsRequest({ datasetId, page, keywords }: DocumentsRequestInput) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const id = datasetId ?? "";
  return useQuery({
    queryKey: documentsQueryKey(tenantId, id, page, keywords),
    queryFn: () => listDocuments({ datasetId: id, page, pageSize: DOCUMENTS_PAGE_SIZE, keywords }),
    retry: false,
    placeholderData: keepPreviousData,
    enabled: tenantId !== null && id !== "",
    refetchInterval: (query) => (query.state.data?.items.some((item) => item.run === "1") ? POLL_INTERVAL_MS : false),
    refetchIntervalInBackground: false,
  });
}

/** One document with its chunking values. Polls while it is parsing. */
export function useDocumentDetailRequest(datasetId: string | undefined, docId: string | undefined, enabled = true) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const dataset = datasetId ?? "";
  const doc = docId ?? "";
  return useQuery({
    queryKey: documentDetailKey(tenantId, dataset, doc),
    queryFn: () => getDocument(dataset, doc),
    retry: false,
    enabled: enabled && tenantId !== null && dataset !== "" && doc !== "",
    refetchInterval: (query) => (query.state.data?.run === "1" ? POLL_INTERVAL_MS : false),
    refetchIntervalInBackground: false,
  });
}

/**
 * Refreshes everything a parse, cancel, switch or settings call can change: documents, the ingestion summary and logs,
 * and both dataset keys. Called from `onSettled`, so a request that timed out on the client still refreshes (FE-03).
 */
export function invalidateParseData(queryClient: QueryClient, tenantId: string | null, datasetId: string): Promise<void> {
  return Promise.all([
    invalidateDocumentData(queryClient, tenantId, datasetId),
    queryClient.invalidateQueries({ queryKey: ingestionKeyRoot(tenantId, datasetId) }),
  ]).then(() => undefined);
}

/**
 * Invalidates the dataset detail and the ingestion summary once when a row that was running on the previous render is
 * not running now, so the totals follow a finished parse without waiting for their own poll.
 */
export function useInvalidateOnParseEnd(datasetId: string | undefined, items: readonly Pick<DocumentView, "id" | "run">[] | undefined): void {
  const queryClient = useQueryClient();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const runningBefore = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (items === undefined) return;
    const now = new Set(items.filter((item) => item.run === "1").map((item) => item.id));
    const ended = items.some((item) => item.run !== "1" && runningBefore.current.has(item.id));
    runningBefore.current = now;
    if (!ended || datasetId === undefined || datasetId === "") return;
    void queryClient.invalidateQueries({ queryKey: datasetQueryKey(tenantId, datasetId) });
    void queryClient.invalidateQueries({ queryKey: [...ingestionKeyRoot(tenantId, datasetId), "summary"] });
  }, [items, datasetId, queryClient, tenantId]);
}

export interface ParseDocumentsInput {
  datasetId: string;
  ids: string[];
  /** "1" starts, "2" cancels. */
  run: "1" | "2";
  confirmReplace?: boolean;
}

/** Starts or cancels parsing. Not retried; refreshes in `onSettled`. */
export function useParseDocumentsRequest() {
  const queryClient = useQueryClient();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useMutation({
    mutationFn: ({ datasetId, ids, run, confirmReplace }: ParseDocumentsInput) => parseDocuments(datasetId, ids, run, confirmReplace === true),
    retry: false,
    gcTime: 0,
    onSettled: (_data, _error, { datasetId }) => invalidateParseData(queryClient, tenantId, datasetId),
  });
}

export interface SetDocumentsEnabledInput {
  datasetId: string;
  ids: string[];
  enabled: boolean;
}

/** Switches documents in or out of search. Not optimistic; refreshes in `onSettled`. */
export function useSetDocumentsEnabledRequest() {
  const queryClient = useQueryClient();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useMutation({
    mutationFn: ({ datasetId, ids, enabled }: SetDocumentsEnabledInput) => setDocumentsEnabled(datasetId, ids, enabled),
    retry: false,
    gcTime: 0,
    onSettled: (_data, _error, { datasetId }) => invalidateParseData(queryClient, tenantId, datasetId),
  });
}

export interface UpdateDocumentSettingsInput {
  datasetId: string;
  docId: string;
  changes: DocumentSettingsChanges;
}

/** Changes a document's chunking method and values. Not retried; refreshes in `onSettled`. */
export function useUpdateDocumentSettingsRequest() {
  const queryClient = useQueryClient();
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  return useMutation({
    mutationFn: ({ datasetId, docId, changes }: UpdateDocumentSettingsInput) => updateDocumentSettings(datasetId, docId, changes),
    retry: false,
    gcTime: 0,
    onSettled: (_data, _error, { datasetId }) => invalidateParseData(queryClient, tenantId, datasetId),
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
