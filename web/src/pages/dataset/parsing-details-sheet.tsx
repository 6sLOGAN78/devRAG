import { useEffect, useId, useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { failureSentence, failureStepKey, isTerminalFailure } from "@/constants/failure-codes";
import { useIngestionLogRequest } from "@/hooks/use-ingestion-request";
import { ApiError } from "@/services/http";
import type { IngestionLogDetail, IngestionLogView } from "@/services/ingestion-service";
import { StatusKindBadge, type StatusKind } from "./document-status-badge";

/** How close to the end of the log box still counts as "at the bottom", in pixels. */
const BOTTOM_SLACK_PX = 8;
const LIST_SKELETONS = 5;

/** The table's status map applied to a log entry: a failed or cancelled run that kept chunks is partly indexed (D-07). */
export function logKindOf(log: Pick<IngestionLogView, "result" | "chunkCount">): StatusKind {
  switch (log.result) {
    case "running":
      return "parsing";
    case "done":
      return "finished";
    case "failed":
      return log.chunkCount > 0 ? "partial" : "failed";
    case "cancelled":
      return log.chunkCount > 0 ? "partial" : "cancelled";
    default:
      return "unknown";
  }
}

/** Seconds with one decimal below 10, whole seconds from 10 up (UI-SPEC "Parsing details panel"). */
export function formatSeconds(seconds: number, language: string): string {
  const value = Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
  const tenths = Math.round(value * 10) / 10;
  if (tenths < 10) return new Intl.NumberFormat(language, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(tenths);
  return new Intl.NumberFormat(language, { maximumFractionDigits: 0 }).format(Math.round(value));
}

/** The reason sentence of a failed entry: fixed copy for a known code, the bounded plain server message otherwise. */
export function useReasonText(error: { code: string; message: string } | null | undefined): string {
  const { t } = useTranslation();
  const sentence = failureSentence(error);
  return "key" in sentence ? t(sentence.key) : sentence.text;
}

/** The log lines, exactly as the server sent them. Follows new lines only while the reader sits at the bottom. */
function LogBox({ lines, running }: { lines: readonly string[]; running: boolean }) {
  const { t } = useTranslation();
  const titleId = useId();
  const box = useRef<HTMLDivElement | null>(null);
  const atBottom = useRef(true);

  useLayoutEffect(() => {
    const element = box.current;
    if (running && element !== null && atBottom.current) element.scrollTop = element.scrollHeight;
  }, [lines, running]);

  return (
    <section className="flex flex-col gap-2">
      <h3 id={titleId} className="text-xs font-semibold">
        {t("datasets.details.log")}
      </h3>
      {lines.length === 0 ? (
        <p data-testid="details-log-empty" className="text-sm font-normal text-muted-foreground">
          {t("datasets.details.logEmpty")}
        </p>
      ) : (
        <div
          ref={box}
          role="region"
          aria-labelledby={titleId}
          tabIndex={0}
          data-testid="details-log"
          onScroll={(event) => {
            const element = event.currentTarget;
            atBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight <= BOTTOM_SLACK_PX;
          }}
          className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words rounded-md border bg-background p-4 font-mono text-sm font-normal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {lines.map((line, index) => (
            <div key={index} className="min-h-5">
              {line}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function Field({ label, testId, children }: { label: string; testId: string; children: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-xs font-normal text-muted-foreground">{label}</dt>
      <dd data-testid={testId} className="break-words text-right text-sm font-semibold tabular-nums">
        {children}
      </dd>
    </div>
  );
}

/** What the sheet shows of one entry. Only the contract's fields are read, and all of them render as text nodes. */
function DetailsContent({ log }: { log: IngestionLogDetail }) {
  const { t, i18n } = useTranslation();
  const failed = log.result === "failed";
  const reason = useReasonText(log.error);
  const code = log.error?.code ?? "";
  const detail = log.error?.detail ?? "";
  const started = log.startedAt > 0 ? new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "short" }).format(new Date(log.startedAt)) : t("common.notSet");

  let retry: string | null = null;
  if (failed && log.retried) retry = t("datasets.details.retried", { count: log.attempts });
  else if (failed && isTerminalFailure(code)) retry = t("datasets.details.notRetried");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col items-start gap-2">
        <StatusKindBadge kind={logKindOf(log)} testId="details-status" />
        {failed ? (
          <p data-testid="details-reason" className="break-words text-sm font-normal">
            {reason}
          </p>
        ) : null}
        {retry === null ? null : (
          <p data-testid="details-retry" className="text-xs font-normal text-muted-foreground">
            {retry}
          </p>
        )}
      </div>
      <dl className="flex flex-col gap-2">
        {failed ? (
          <Field label={t("datasets.details.field.step")} testId="details-step">
            {t(failureStepKey(log.error?.step ?? ""))}
          </Field>
        ) : null}
        <Field label={t("datasets.details.field.attempts")} testId="details-attempts">
          {t("datasets.details.field.attemptsValue", { used: log.attempts, max: log.maxAttempts })}
        </Field>
        <Field label={t("datasets.details.field.started")} testId="details-started">
          {started}
        </Field>
        <Field label={t("datasets.details.field.duration")} testId="details-duration">
          {t("datasets.details.field.durationValue", { seconds: formatSeconds(log.durationSeconds, i18n.language) })}
        </Field>
        <Field label={t("datasets.details.field.indexed")} testId="details-chunks">
          {new Intl.NumberFormat(i18n.language).format(log.chunkCount)}
        </Field>
        {log.pagesTotal !== null && log.pagesWithoutText !== null ? (
          <Field label={t("datasets.details.field.pages")} testId="details-pages">
            {t("datasets.details.field.pagesValue", { skipped: log.pagesWithoutText, total: log.pagesTotal })}
          </Field>
        ) : null}
      </dl>
      {failed && detail !== "" ? (
        <section className="flex flex-col gap-1">
          <h3 className="text-xs font-semibold">{t("datasets.details.providerMessage")}</h3>
          <p data-testid="details-provider-message" className="break-words text-sm font-normal text-muted-foreground">
            {detail}
          </p>
        </section>
      ) : null}
      <LogBox lines={log.log} running={log.result === "running"} />
    </div>
  );
}

function PanelSkeleton() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4">
      <p role="status" className="sr-only">
        {t("datasets.details.loading")}
      </p>
      <div className="flex flex-col gap-2">
        {Array.from({ length: LIST_SKELETONS }, (_, index) => (
          <Skeleton key={index} data-testid="details-skeleton" className="h-5 w-full" aria-hidden="true" />
        ))}
      </div>
      <Skeleton data-testid="details-log-skeleton" className="h-40 w-full" aria-hidden="true" />
    </div>
  );
}

interface PanelProps {
  datasetId: string;
  logId: string;
  enabled: boolean;
  canParseAgain?: (log: IngestionLogDetail) => boolean;
  onParseAgain: (documentId: string) => void;
}

/** Everything inside the open sheet. Keyed by the log id, so a request error never outlives its entry (FE-04). */
function DetailsPanel({ datasetId, logId, enabled, canParseAgain, onParseAgain }: PanelProps) {
  const { t } = useTranslation();
  const request = useIngestionLogRequest(datasetId, logId, enabled);
  const log = request.data;
  const gone = request.isError && request.error instanceof ApiError && request.error.status === 404;

  let body;
  if (log !== undefined) body = <DetailsContent log={log} />;
  else if (gone) {
    body = (
      <p data-testid="details-gone" className="text-sm font-normal text-muted-foreground">
        {t("datasets.details.gone")}
      </p>
    );
  } else if (request.isError) {
    body = (
      <div data-testid="details-error">
        <ErrorState heading={t("datasets.details.error.heading")} onAction={() => void request.refetch()} />
      </div>
    );
  } else body = <PanelSkeleton />;

  return (
    <>
      <SheetHeader className="pr-8">
        <SheetTitle>{t("datasets.details.title")}</SheetTitle>
        <SheetDescription className="break-all">{log?.documentName ?? ""}</SheetDescription>
      </SheetHeader>
      <div className="mt-4 min-h-0 flex-1 overflow-y-auto">{body}</div>
      <div className="mt-4 flex justify-end gap-2">
        {log !== undefined && canParseAgain?.(log) === true ? (
          <Button type="button" variant="outline" data-testid="details-reparse" onClick={() => onParseAgain(log.documentId)}>
            {t("datasets.parse.again")}
          </Button>
        ) : null}
        <SheetClose asChild>
          <Button type="button" variant="ghost" data-testid="details-close">
            {t("dialog.close")}
          </Button>
        </SheetClose>
      </div>
    </>
  );
}

/** Reports the moment the sheet's content has left the page: it unmounts only after the close animation. */
function ExitWatcher({ onExit }: { onExit: () => void }) {
  const ref = useRef(onExit);
  ref.current = onExit;
  useEffect(() => () => ref.current(), []);
  return null;
}

export interface ParsingDetailsSheetProps {
  datasetId: string;
  /** The entry on show. Kept after closing so the sheet can slide out with its content; nothing loads while closed. */
  logId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The owner puts focus back on what opened the sheet (R-152). */
  onCloseAutoFocus?: (event: Event) => void;
  /** False until the workspace is bound (FE-02). */
  enabled?: boolean;
  /** May the caller parse this entry's document again? Absent: the button is never drawn. */
  canParseAgain?: (log: IngestionLogDetail) => boolean;
  /** Called once the sheet is gone after "Parse again", so the confirmation dialog is never stacked over it (R-152). */
  onParseAgain?: (documentId: string) => void;
}

/**
 * The parsing details of one run (UI-15, D-08): a right-hand sheet that is a Dialog, so nothing is stacked over it. Its
 * body is mounted only while open and keyed by the entry. "Parse again" closes the sheet first and hands the request to
 * the owner only after the sheet has unmounted.
 */
export function ParsingDetailsSheet({ datasetId, logId, open, onOpenChange, onCloseAutoFocus, enabled = true, canParseAgain, onParseAgain }: ParsingDetailsSheetProps) {
  const { t } = useTranslation();
  const pending = useRef<string | null>(null);
  const openRef = useRef(open);
  openRef.current = open;
  const parseAgainRef = useRef(onParseAgain);
  parseAgainRef.current = onParseAgain;

  function exited(): void {
    // Unmounting while still open (the page left) is not a close: nothing is sent then.
    if (openRef.current) return;
    const documentId = pending.current;
    pending.current = null;
    if (documentId !== null) parseAgainRef.current?.(documentId);
  }

  return (
    <Sheet open={open && logId !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" closeLabel={t("dialog.close")} data-testid="parsing-details" onCloseAutoFocus={onCloseAutoFocus} className="gap-0 overflow-hidden">
        <ExitWatcher onExit={exited} />
        {logId === null ? null : (
          <DetailsPanel
            key={logId}
            datasetId={datasetId}
            logId={logId}
            enabled={enabled}
            canParseAgain={canParseAgain}
            onParseAgain={(documentId) => {
              pending.current = documentId;
              onOpenChange(false);
            }}
          />
        )}
      </SheetContent>
    </Sheet>
  );
}
