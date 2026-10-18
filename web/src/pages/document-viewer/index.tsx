import { ChevronLeft, FileX2 } from "lucide-react";
import { useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { ImagePreview } from "@/components/document-preview/image-preview";
import { PagePreview } from "@/components/document-preview/page-preview";
import { TextPreview } from "@/components/document-preview/text-preview";
import { useDownload } from "@/components/document-preview/use-download";
import { EmptyState } from "@/components/empty-state";
import { formatBytes } from "@/components/file-upload-dialog/file-rules";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { chunkPath, datasetFilesPath } from "@/constants/app-paths";
import { METHOD_STEMS, isChunkMethod } from "@/constants/chunk-methods";
import { useDatasetBinding } from "@/hooks/use-dataset-binding";
import { useDocumentDetailRequest } from "@/hooks/use-document-request";
import type { DatasetDetailView } from "@/services/dataset-service";
import type { DocumentDetailView } from "@/services/document-service";
import { InspectorNotFound, typeLabelOf } from "../chunk/inspector-states";
import { StatusKindBadge, statusKindOf } from "../dataset/document-status-badge";
import { datasetPageState } from "../dataset/errors";
import { DownloadButton } from "./download-button";

const HEX_ID = /^[0-9a-f]{32}$/;
const MAX_PAGE = 100000;
const TEXT_TYPES = ["txt", "md", "markdown", "csv", "json", "html", "htm"];
const IMAGE_TYPES = ["jpg", "jpeg", "png"];

type BodyKind = "pages" | "text" | "image" | "none";

/** The body for a file: by its extension, with a PDF needing page images to show anything. */
function bodyKindOf(doc: DocumentDetailView): BodyKind {
  const type = typeLabelOf(doc.suffix).toLowerCase();
  if (type === "pdf") return doc.preview === "pages" && (doc.pagesTotal ?? 0) >= 1 ? "pages" : "none";
  if (TEXT_TYPES.includes(type)) return "text";
  if (IMAGE_TYPES.includes(type)) return "image";
  return "none";
}

/** `page` from the address: a whole number of at least 1, otherwise 1. */
function parsePage(raw: string | null): number {
  if (raw === null || !/^\d{1,9}$/.test(raw)) return 1;
  return Math.min(MAX_PAGE, Math.max(1, Number(raw)));
}

function uploadedOf(doc: DocumentDetailView, language: string): { iso: string; text: string } | null {
  const stamp = doc.createTime > 0 ? doc.createTime : doc.updateTime;
  if (stamp <= 0) return null;
  const date = new Date(stamp);
  if (Number.isNaN(date.getTime())) return null;
  return { iso: date.toISOString(), text: new Intl.DateTimeFormat(language, { dateStyle: "medium" }).format(date) };
}

function ViewerSkeleton() {
  const { t } = useTranslation();
  return (
    <div data-testid="viewer-skeleton" className="flex flex-col gap-6">
      <p role="status" className="sr-only">
        {t("viewer.loading")}
      </p>
      <Skeleton className="h-8 w-64" aria-hidden="true" />
      <Skeleton className="h-4 w-80" aria-hidden="true" />
      <Skeleton className="mx-auto h-[40vh] min-h-[240px] w-full max-w-4xl" aria-hidden="true" />
    </div>
  );
}

function MetaItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-1">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

interface BodyProps {
  dataset: DatasetDetailView;
  doc: DocumentDetailView;
  page: number;
  onPageChange: (page: number) => void;
}

function ViewerBody({ dataset, doc, page, onPageChange }: BodyProps) {
  const { t, i18n } = useTranslation();
  const download = useDownload(dataset.id, doc.id, doc.name);
  const kind = bodyKindOf(doc);
  const type = typeLabelOf(doc.suffix);
  const uploaded = uploadedOf(doc, i18n.language);
  const methodLabel = isChunkMethod(doc.parserId) ? t(`datasets.chunking.method.${METHOD_STEMS[doc.parserId]}.title`) : doc.parserId;
  const pages = doc.pagesTotal ?? 0;

  useEffect(() => {
    document.title = t("viewer.documentTitle", { name: doc.name });
  }, [doc.name, t, i18n.language]);

  let body: React.ReactNode;
  switch (kind) {
    case "pages":
      body = (
        <div data-testid="viewer-pages" className="mx-auto w-full max-w-4xl">
          <PagePreview datasetId={dataset.id} docId={doc.id} name={doc.name} pages={pages} page={Math.min(page, pages)} onPageChange={onPageChange} />
        </div>
      );
      break;
    case "text":
      body = (
        <div className="max-w-4xl">
          <TextPreview datasetId={dataset.id} docId={doc.id} />
        </div>
      );
      break;
    case "image":
      body = (
        <div className="max-w-4xl">
          <ImagePreview datasetId={dataset.id} docId={doc.id} name={doc.name} />
        </div>
      );
      break;
    default:
      body = (
        <Card data-testid="viewer-no-preview" className="mx-auto w-full max-w-4xl">
          <EmptyState
            as="h2"
            icon={FileX2}
            heading={t("viewer.none.heading", { type })}
            body={doc.parseable ? t("viewer.none.body") : t("viewer.none.bodyUnparsed")}
            action={<DownloadButton download={download} name={doc.name} testId="viewer-download-card" named={false} />}
          />
        </Card>
      );
  }

  return (
    <div data-testid="viewer-page" className="flex flex-col gap-6">
      <Link
        to={datasetFilesPath(dataset.id)}
        data-testid="viewer-back"
        className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-normal text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <ChevronLeft className="size-4" aria-hidden="true" />
        <span className="break-all">{dataset.name}</span>
      </Link>
      <PageHeader
        title={doc.name}
        titleHint={doc.name}
        titleClassName="line-clamp-2 break-all"
        actions={
          <>
            <Button asChild variant="outline">
              <Link to={chunkPath(dataset.id, doc.id)} data-testid="viewer-chunks-link">
                {t("viewer.viewChunks")}
              </Link>
            </Button>
            <DownloadButton download={download} name={doc.name} testId="viewer-download" named />
          </>
        }
      />
      <dl data-testid="viewer-meta" className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs font-normal">
        <MetaItem label={t("viewer.meta.type")}>{type}</MetaItem>
        <MetaItem label={t("viewer.meta.size")}>
          <span className="tabular-nums">{formatBytes(doc.size, i18n.language)}</span>
        </MetaItem>
        <MetaItem label={t("viewer.meta.uploaded")}>{uploaded === null ? t("common.notSet") : <time dateTime={uploaded.iso}>{uploaded.text}</time>}</MetaItem>
        <MetaItem label={t("viewer.meta.status")}>
          <StatusKindBadge kind={statusKindOf(doc)} />
        </MetaItem>
        <MetaItem label={t("viewer.meta.chunkTotal")}>{new Intl.NumberFormat(i18n.language).format(doc.chunkCount)}</MetaItem>
        <MetaItem label={t("viewer.meta.method")}>{methodLabel}</MetaItem>
      </dl>
      {body}
    </div>
  );
}

/**
 * The document viewer (UI-19, DOC-21) at `/document?id=&doc=`: the original beside no chunks. It binds the workspace
 * before any request (FE-02). PDFs show their page images, text-like files their text (as text, never as markup), images
 * themselves; every other type offers a download. Files are never opened inline as HTML.
 */
export default function DocumentViewerPage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const rawId = params.get("id") ?? "";
  const rawDoc = params.get("doc") ?? "";
  const valid = HEX_ID.test(rawId) && HEX_ID.test(rawDoc);
  const page = parsePage(params.get("page"));

  const binding = useDatasetBinding({ datasetId: valid ? rawId : "" });
  const { dataset, bound } = binding;
  const detail = useDocumentDetailRequest(dataset?.id, rawDoc, bound && valid);
  const doc = detail.data;

  useEffect(() => {
    if (doc === undefined) document.title = t("viewer.documentTitleFallback");
  }, [doc, t, i18n.language]);

  const setPage = useCallback(
    (next: number) =>
      setParams(
        (current) => {
          const updated = new URLSearchParams(current);
          if (next <= 1) updated.delete("page");
          else updated.set("page", String(next));
          return updated;
        },
        { replace: true },
      ),
    [setParams],
  );

  const notFound = (
    <div data-testid="viewer-not-found">
      <InspectorNotFound />
    </div>
  );
  if (!valid || binding.state === "not-found" || binding.unbindable) return notFound;
  if (dataset === undefined) {
    if (binding.state === "error") return <ErrorState level="h1" heading={t("inspector.error.pageHeading")} onAction={binding.refetch} />;
    return <ViewerSkeleton />;
  }
  if (doc === undefined) {
    if (detail.isError) {
      if (datasetPageState(detail.error) === "notFound") return notFound;
      return <ErrorState level="h1" heading={t("inspector.error.pageHeading")} onAction={() => void detail.refetch()} />;
    }
    return <ViewerSkeleton />;
  }
  return <ViewerBody key={`${dataset.id}:${doc.id}`} dataset={dataset} doc={doc} page={page} onPageChange={setPage} />;
}
