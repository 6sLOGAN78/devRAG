import { ChevronLeft, ScrollText } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Pagination } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { datasetFilesPath } from "@/constants/app-paths";
import { useDatasetBinding } from "@/hooks/use-dataset-binding";
import { LOGS_PAGE_SIZE, useIngestionLogsRequest } from "@/hooks/use-ingestion-request";
import type { IngestionLogView } from "@/services/ingestion-service";
import { StatusKindBadge, type StatusKind } from "../document-status-badge";
import { DatasetNotFound } from "../page-states";
import { ParsingDetailsSheet, formatSeconds, useReasonText } from "../parsing-details-sheet";

const SKELETON_ROWS = 5;
const COLUMNS = ["file", "started", "duration", "result", "attempts", "actions"] as const;
/** An absurd `page` in the address is capped here; the server answers an empty page and the table steps back. */
const MAX_PAGE = 100000;

/** `page` from the address: a whole number of at least 1, otherwise 1. */
function parsePage(raw: string | null): number {
  if (raw === null || !/^\d{1,9}$/.test(raw)) return 1;
  return Math.min(MAX_PAGE, Math.max(1, Number(raw)));
}

/** The four results of the log (UI-SPEC "Screen: Parsing log"); anything else keeps an unexpected value visible. */
function resultKindOf(result: string): StatusKind {
  switch (result) {
    case "running":
      return "parsing";
    case "done":
      return "finished";
    case "failed":
      return "failed";
    case "cancelled":
      return "cancelled";
    default:
      return "unknown";
  }
}

function LogsSkeleton() {
  const { t } = useTranslation();
  return (
    <div data-testid="logs-skeleton" className="flex flex-col">
      <p role="status" className="sr-only">
        {t("datasets.ingestion.log.loading")}
      </p>
      <Skeleton className="h-10 w-full rounded-none" aria-hidden="true" />
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <Skeleton key={index} data-testid="log-row-skeleton" className="h-12 w-full rounded-none border-b border-background" aria-hidden="true" />
      ))}
    </div>
  );
}

function LogRow({ log, onShow }: { log: IngestionLogView; onShow: (logId: string, opener: HTMLElement) => void }) {
  const { t, i18n } = useTranslation();
  const failed = log.result === "failed";
  const reason = useReasonText(log.error);
  const started = log.startedAt > 0 ? new Date(log.startedAt) : null;
  const startedText = started === null || Number.isNaN(started.getTime()) ? null : new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "short" }).format(started);
  return (
    <TableRow data-testid="log-row" data-log-id={log.id} className="min-h-12">
      <TableCell>
        <span className="line-clamp-2 break-all">{log.documentName}</span>
      </TableCell>
      <TableCell className="whitespace-nowrap">{started === null || startedText === null ? t("common.notSet") : <time dateTime={started.toISOString()}>{startedText}</time>}</TableCell>
      <TableCell className="whitespace-nowrap tabular-nums">{t("datasets.details.field.durationValue", { seconds: formatSeconds(log.durationSeconds, i18n.language) })}</TableCell>
      <TableCell>
        <div className="flex flex-col items-start gap-1">
          <StatusKindBadge kind={resultKindOf(log.result)} testId="log-result" />
          {failed ? <p className="line-clamp-2 break-words text-xs font-normal text-destructive">{reason}</p> : null}
        </div>
      </TableCell>
      <TableCell className="whitespace-nowrap tabular-nums">{t("datasets.details.field.attemptsValue", { used: log.attempts, max: log.maxAttempts })}</TableCell>
      <TableCell className="text-right">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          data-testid="log-details"
          aria-label={t("datasets.files.detailsLabel", { name: log.documentName })}
          onClick={(event) => onShow(log.id, event.currentTarget)}
        >
          {t("datasets.files.detailsLink")}
        </Button>
      </TableCell>
    </TableRow>
  );
}

/**
 * The parsing log of a dataset (KB-15) at `/dataset/logs?id=`: every run, newest first, 20 a page. It binds the workspace
 * like the dataset page and sends no request before it is bound (FE-02). File names, reasons and log lines are server or
 * user text and render as text nodes only.
 */
export default function ParsingLogPage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const raw = params.get("id") ?? "";
  const page = parsePage(params.get("page"));
  const binding = useDatasetBinding({ datasetId: raw });
  const { dataset, bound } = binding;
  const logs = useIngestionLogsRequest(dataset?.id, page, bound);

  const opener = useRef<HTMLElement | null>(null);
  const [logId, setLogId] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const items = logs.data?.items ?? [];
  const total = logs.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / LOGS_PAGE_SIZE));
  const pastEnd = logs.data !== undefined && items.length === 0 && total > 0 && page > pages;

  const setPage = useCallback(
    (next: number, options?: { replace?: boolean }) => {
      setParams(
        (current) => {
          const updated = new URLSearchParams(current);
          if (next <= 1) updated.delete("page");
          else updated.set("page", String(next));
          return updated;
        },
        { replace: options?.replace === true },
      );
    },
    [setParams],
  );

  useEffect(() => {
    if (pastEnd) setPage(pages, { replace: true });
  }, [pastEnd, pages, setPage]);

  const name = dataset?.name;
  useEffect(() => {
    document.title = name === undefined ? t("datasets.ingestion.log.documentTitleFallback") : t("datasets.ingestion.log.documentTitle", { name });
  }, [name, t, i18n.language]);

  if (binding.state === "not-found" || binding.unbindable) return <DatasetNotFound />;
  if (dataset === undefined && binding.state === "error") return <ErrorState level="h1" heading={t("dataset.error.heading")} onAction={binding.refetch} />;

  function show(id: string, button: HTMLElement): void {
    opener.current = button;
    setLogId(id);
    setOpen(true);
  }

  function restoreFocus(event: Event): void {
    event.preventDefault();
    if (opener.current?.isConnected === true) opener.current.focus();
  }

  let body;
  if (dataset === undefined || !bound || logs.isPending || pastEnd) {
    body = <LogsSkeleton />;
  } else if (logs.isError && logs.data === undefined) {
    body = (
      <div className="p-6">
        <ErrorState heading={t("datasets.ingestion.log.error.heading")} onAction={() => void logs.refetch()} />
      </div>
    );
  } else if (items.length === 0) {
    body = (
      <EmptyState
        as="h2"
        icon={ScrollText}
        heading={t("datasets.ingestion.log.empty.heading")}
        body={t("datasets.ingestion.log.empty.body")}
        action={
          <Button asChild variant="link">
            <Link to={datasetFilesPath(dataset.id)}>{t("datasets.ingestion.log.empty.action")}</Link>
          </Button>
        }
      />
    );
  } else {
    body = (
      <Table data-testid="logs-table">
        <TableCaption className="sr-only">{t("datasets.ingestion.log.caption", { name: dataset.name })}</TableCaption>
        <TableHeader>
          <TableRow className="h-10">
            {COLUMNS.map((column) => (
              <TableHead key={column} className={column === "actions" ? "text-right" : undefined}>
                {t(`datasets.ingestion.log.col.${column}`)}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((log) => (
            <LogRow key={log.id} log={log} onShow={show} />
          ))}
        </TableBody>
      </Table>
    );
  }

  return (
    <div data-testid="logs-page" className="flex flex-col gap-6">
      {dataset === undefined ? null : (
        <Link
          to={datasetFilesPath(dataset.id)}
          data-testid="logs-back"
          className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-normal text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          <ChevronLeft className="size-4" aria-hidden="true" />
          <span className="break-all">{dataset.name}</span>
        </Link>
      )}
      <PageHeader title={t("datasets.ingestion.log.title")} />
      {dataset === undefined ? null : <p className="break-words text-sm font-normal text-muted-foreground">{t("datasets.ingestion.log.intro", { dataset: dataset.name })}</p>}
      <Card className="overflow-x-auto">{body}</Card>
      {logs.data !== undefined && !pastEnd && items.length > 0 ? (
        <Pagination
          aria-label={t("datasets.ingestion.log.pages")}
          page={page}
          pages={pages}
          onPageChange={setPage}
          previousLabel={t("common.pagination.previous")}
          nextLabel={t("common.pagination.next")}
          statusLabel={t("common.pagination.status", { page, pages })}
        />
      ) : null}
      {dataset === undefined ? null : <ParsingDetailsSheet datasetId={dataset.id} logId={logId} open={open} onOpenChange={setOpen} onCloseAutoFocus={restoreFocus} enabled={bound} />}
    </div>
  );
}
