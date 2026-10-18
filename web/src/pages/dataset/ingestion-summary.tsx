import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { datasetLogsPath } from "@/constants/app-paths";
import { useIngestionSummaryRequest } from "@/hooks/use-ingestion-request";
import type { IngestionSummary as Summary } from "@/services/ingestion-service";

/** The eight values in the order of the UI-SPEC; `id` is the test id suffix and the locale leaf, `field` the summary field. */
const ENTRIES: ReadonlyArray<{ id: string; leaf: string; field: keyof Summary }> = [
  { id: "unstart", leaf: "unstart", field: "unstart" },
  { id: "running", leaf: "running", field: "running" },
  { id: "done", leaf: "done", field: "done" },
  { id: "failed", leaf: "failed", field: "failed" },
  { id: "cancelled", leaf: "cancelled", field: "cancelled" },
  { id: "partial", leaf: "partial", field: "partial" },
  { id: "chunk-total", leaf: "chunkTotal", field: "chunkTotal" },
  { id: "token-total", leaf: "tokenTotal", field: "tokenTotal" },
];

/**
 * Counts of the dataset's documents by parse state (KB-14). It owns its query, so a failure here shows one line in the
 * card and leaves the table alone. The caller does not render it for an empty dataset. Token totals are a labelled
 * pair, never "{count} tokens".
 */
export function IngestionSummary({ datasetId }: { datasetId: string }) {
  const { t, i18n } = useTranslation();
  const summary = useIngestionSummaryRequest(datasetId);
  const number = new Intl.NumberFormat(i18n.language);
  const data = summary.data;
  return (
    <Card data-testid="ingestion-summary" className="flex flex-col gap-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold leading-tight">{t("datasets.ingestion.title")}</h2>
        <Link
          to={datasetLogsPath(datasetId)}
          data-testid="ingestion-log-link"
          className="rounded-sm text-sm font-normal text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          {t("datasets.ingestion.logLink")}
        </Link>
      </div>
      {data === undefined && summary.isError ? (
        <div className="flex flex-wrap items-center gap-2 text-sm font-normal">
          <p data-testid="ingestion-summary-error">{t("datasets.ingestion.summaryError")}</p>
          <Button type="button" variant="ghost" size="sm" onClick={() => void summary.refetch()}>
            {t("errorState.action")}
          </Button>
        </div>
      ) : (
        <dl className="flex flex-wrap gap-x-8 gap-y-3">
          {ENTRIES.map((entry) => (
            <div key={entry.id} className="flex flex-col gap-1">
              <dt className="text-xs font-semibold text-muted-foreground">{t(`datasets.ingestion.count.${entry.leaf}`)}</dt>
              {data === undefined ? (
                <dd>
                  <Skeleton data-testid="summary-skeleton" className="h-4 w-8" aria-hidden="true" />
                </dd>
              ) : (
                <dd data-testid={`summary-count-${entry.id}`} className="text-sm font-semibold tabular-nums">
                  {number.format(data[entry.field])}
                </dd>
              )}
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}
