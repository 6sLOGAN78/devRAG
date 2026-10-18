import { CircleAlert, CircleSlash, Info, Loader2, Rows3, SearchX } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { DATASETS_PATH } from "@/constants/app-paths";
import type { DocumentDetailView } from "@/services/document-service";
import { percentOf } from "../dataset/document-progress";
import { useReasonText } from "../dataset/parsing-details-sheet";

/** The upper-cased extension (`PDF`, `DOCX`) the copy names a file type with. One helper, so every sentence agrees. */
export function typeLabelOf(suffix: string): string {
  return suffix.replace(/^\./, "").toUpperCase();
}

const SKELETON_CARDS = 5;

/** Five card-shaped placeholders for the first load of the list. */
export function ChunkListSkeleton() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-3">
      <p role="status" className="sr-only">
        {t("inspector.loading")}
      </p>
      {Array.from({ length: SKELETON_CARDS }, (_, index) => (
        <Skeleton key={index} data-testid="chunk-card-skeleton" className="h-24 w-full" aria-hidden="true" />
      ))}
    </div>
  );
}

/** The list could not be loaded: in place, so search, filter and pager stay where they are. */
export function ChunkListError({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div data-testid="chunk-list-error">
      <ErrorState heading={t("inspector.error.listHeading")} onAction={onRetry} />
    </div>
  );
}

/** Nothing matches the search or the filter, or nothing is switched off. */
export function NoChunks({ kind, onClear }: { kind: "noMatch" | "noneOff"; onClear: () => void }) {
  const { t } = useTranslation();
  return (
    <div data-testid="chunk-empty" data-kind={kind}>
      <EmptyState
        as="h2"
        icon={SearchX}
        heading={t(`inspector.${kind}.heading`)}
        body={kind === "noMatch" ? t("inspector.noMatch.body") : undefined}
        action={
          <Button type="button" variant="link" onClick={onClear}>
            {t("inspector.noMatch.action")}
          </Button>
        }
      />
    </div>
  );
}

export type EmptyDocumentInput = Pick<DocumentDetailView, "name" | "suffix" | "run" | "parseable" | "progress" | "progressMessage" | "error" | "chunkCount" | "lastLogId">;

export interface DocumentEmptyProps {
  document: EmptyDocumentInput;
  /** The caller may parse and cancel this document. */
  canChange: boolean;
  /** A parse or cancel request is in flight. */
  busy: boolean;
  onParse: () => void;
  onCancel: () => void;
  /** Receives the link-button so focus can return to it when the sheet closes. */
  onDetails: (opener: HTMLElement) => void;
}

type EmptyKind = "never" | "unavailable" | "parsing" | "failed" | "cancelled";

function kindOf(document: EmptyDocumentInput): EmptyKind {
  if (document.run === "1") return "parsing";
  if (document.run === "4") return "failed";
  if (document.run === "2") return "cancelled";
  return document.parseable ? "never" : "unavailable";
}

/**
 * What the inspector says in place of the list when the document has no chunks and no search or filter is active. The
 * parse buttons are the same requests as the row's and go through the owner's `useParseActions`.
 */
export function DocumentEmpty({ document, canChange, busy, onParse, onCancel, onDetails }: DocumentEmptyProps) {
  const { t } = useTranslation();
  const reason = useReasonText(document.error);
  const kind = kindOf(document);

  const parse = (label: string) => (
    <Button type="button" data-testid="chunk-empty-parse" aria-disabled={busy} aria-busy={busy ? "true" : undefined} onClick={() => !busy && onParse()}>
      {label}
    </Button>
  );

  let content;
  switch (kind) {
    case "never":
      content = (
        <EmptyState
          as="h2"
          icon={Rows3}
          heading={t("inspector.empty.heading")}
          body={canChange ? t("inspector.empty.body") : t("inspector.empty.bodyReadOnly")}
          action={canChange ? parse(t("inspector.empty.parse")) : undefined}
        />
      );
      break;
    case "unavailable":
      content = <EmptyState as="h2" icon={CircleSlash} heading={t("inspector.unavailable.heading")} body={t("inspector.unavailable.body", { type: typeLabelOf(document.suffix) })} />;
      break;
    case "parsing": {
      const percent = percentOf(document);
      const message = document.progressMessage !== "" ? document.progressMessage : t("datasets.files.progress.waiting");
      content = (
        <EmptyState
          as="h2"
          icon={Loader2}
          heading={t("inspector.parsing.heading")}
          action={
            <div className="flex w-72 max-w-full flex-col items-center gap-2">
              <div className="flex w-full items-center gap-2">
                <Progress value={percent} label={t("datasets.files.progress.label", { name: document.name })} />
                <span className="text-xs font-normal tabular-nums">{t("datasets.files.progress.percent", { percent })}</span>
              </div>
              <p className="max-w-full break-words text-xs font-normal text-muted-foreground">{message}</p>
              {canChange ? (
                <Button type="button" variant="outline" aria-disabled={busy} aria-busy={busy ? "true" : undefined} onClick={() => !busy && onCancel()}>
                  {t("datasets.parse.cancel")}
                </Button>
              ) : null}
            </div>
          }
        />
      );
      break;
    }
    case "failed":
      content = (
        <EmptyState
          as="h2"
          icon={CircleAlert}
          heading={t("inspector.failed.heading")}
          body={reason}
          action={
            canChange || document.lastLogId !== null ? (
              <div className="flex flex-col items-center gap-1">
                {canChange ? parse(t("datasets.parse.again")) : null}
                {document.lastLogId !== null ? (
                  <Button type="button" variant="link" onClick={(event) => onDetails(event.currentTarget)}>
                    {t("datasets.files.menu.details")}
                  </Button>
                ) : null}
              </div>
            ) : undefined
          }
        />
      );
      break;
    case "cancelled":
      content = <EmptyState as="h2" icon={CircleSlash} heading={t("inspector.cancelled.heading")} body={t("inspector.cancelled.body")} action={canChange ? parse(t("datasets.parse.again")) : undefined} />;
      break;
  }
  return (
    <div data-testid="chunk-empty" data-kind={kind}>
      {content}
    </div>
  );
}

/** One identical page for a document that is missing, deleted, private, in another workspace or named by a malformed id. */
export function InspectorNotFound() {
  const { t } = useTranslation();
  return (
    <div data-testid="chunk-not-found">
      <EmptyState
        icon={SearchX}
        heading={t("inspector.notFound.heading")}
        body={t("inspector.notFound.body")}
        action={
          <Button asChild>
            <Link to={DATASETS_PATH}>{t("dataset.notFound.action")}</Link>
          </Button>
        }
      />
    </div>
  );
}

/** The one line shown instead of a preview pane for formats without page geometry. */
export function NoPreviewNote({ type }: { type: string }) {
  const { t } = useTranslation();
  return (
    <p data-testid="no-preview-note" className="flex items-start gap-2 text-xs font-normal text-muted-foreground">
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{t("inspector.preview.none", { type })}</span>
    </p>
  );
}

