import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getIngestionLog, getIngestionSummary, listIngestionLogs } from "@/services/ingestion-service";
import { useActiveWorkspace } from "./use-workspaces";

/** Poll interval of everything that shows a parse in progress (UI-SPEC "Live progress is polling"). */
export const POLL_INTERVAL_MS = 2000;
/** Parsing log rows per page (UI-SPEC). */
export const LOGS_PAGE_SIZE = 20;

/** Every ingestion key of one dataset starts with this prefix, so one invalidation reaches the summary and the logs. */
export const ingestionKeyRoot = (tenantId: string | null, datasetId: string) => ["ws", tenantId, "ingestion", datasetId] as const;
export const ingestionSummaryKey = (tenantId: string | null, datasetId: string) => [...ingestionKeyRoot(tenantId, datasetId), "summary"] as const;
export const ingestionLogsKey = (tenantId: string | null, datasetId: string, page: number) => [...ingestionKeyRoot(tenantId, datasetId), "logs", page] as const;
export const ingestionLogKey = (tenantId: string | null, datasetId: string, logId: string) => [...ingestionKeyRoot(tenantId, datasetId), "log", logId] as const;

/** Counts of documents by parse state. Polls while something runs, never in a hidden tab. */
export function useIngestionSummaryRequest(datasetId: string | undefined, enabled = true) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const id = datasetId ?? "";
  return useQuery({
    queryKey: ingestionSummaryKey(tenantId, id),
    queryFn: () => getIngestionSummary(id),
    retry: false,
    enabled: enabled && tenantId !== null && id !== "",
    refetchInterval: (query) => ((query.state.data?.running ?? 0) > 0 ? POLL_INTERVAL_MS : false),
    refetchIntervalInBackground: false,
  });
}

/** One page of parsing runs. Keeps the previous page while the next loads; polls while any row on the page runs. */
export function useIngestionLogsRequest(datasetId: string | undefined, page: number, enabled = true) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const id = datasetId ?? "";
  return useQuery({
    queryKey: ingestionLogsKey(tenantId, id, page),
    queryFn: () => listIngestionLogs(id, page, LOGS_PAGE_SIZE),
    retry: false,
    placeholderData: keepPreviousData,
    enabled: enabled && tenantId !== null && id !== "",
    refetchInterval: (query) => (query.state.data?.items.some((row) => row.result === "running") ? POLL_INTERVAL_MS : false),
    refetchIntervalInBackground: false,
  });
}

/** One parsing run with its log lines. Polls while the entry runs. */
export function useIngestionLogRequest(datasetId: string | undefined, logId: string | null | undefined, enabled = true) {
  const tenantId = useActiveWorkspace()?.tenantId ?? null;
  const id = datasetId ?? "";
  const log = logId ?? "";
  return useQuery({
    queryKey: ingestionLogKey(tenantId, id, log),
    queryFn: () => getIngestionLog(id, log),
    retry: false,
    enabled: enabled && tenantId !== null && id !== "" && log !== "",
    refetchInterval: (query) => (query.state.data?.result === "running" ? POLL_INTERVAL_MS : false),
    refetchIntervalInBackground: false,
  });
}
